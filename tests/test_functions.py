import pytest
import datetime
from unittest.mock import Mock, patch, call

from flask import request

import app.functions
from app.db import db
from app.functions import *
from app.models import User, WashingCycle, WashingCycleSplit, ScheduleEvent
from app.forms import SplitCycleForm


@patch('app.functions.trigger_relay')
@patch('app.functions.flash')
@patch('app.functions.CeleryTask')
def test_start_cycle(mock_celery_task, mock_flash, mock_trigger_relay, app):
    """ Testing start cycle function in normal conditions. """
    with app.test_request_context():
        user = User.query.first()
        mock_trigger_relay.return_value = 200

        start_cycle(user)

        cycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()

        assert cycle is not None
        assert mock_celery_task.start_cycle_end_notification_task.called
        assert mock_flash.call_count == 1
        mock_flash.assert_called_with('Cycle successfully started!', category='toast-success')


@patch('app.functions.trigger_relay')
@patch('app.functions.flash')
@patch('app.functions.CeleryTask')
def test_start_cycle_trigger_fail(mock_celery_task, mock_flash, mock_trigger_relay, app):
    """ Testing start cycle function with relay trigger fail. """
    with app.test_request_context():
        user = User.query.first()
        mock_trigger_relay.return_value = 500

        with pytest.raises(ChildProcessError):
            start_cycle(user)

        cycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()

        assert cycle is None
        assert mock_celery_task.start_cycle_end_notification_task.called is False
        assert mock_flash.call_count == 1
        mock_flash.assert_called_with('Request to turn on the relay failed!\nPlease try again!', category='toast-error')


@patch('app.functions.flash')
@patch('app.functions.CeleryTask')
def test_start_cycle_already_running(mock_celery_task, mock_flash, app):
    """ Testing start cycle function when a cycle is already running. """
    with app.test_request_context():
        user = User.query.first()
        db.session.add(WashingCycle(user_id=user.id, start_timestamp=datetime.datetime.now()))
        db.session.commit()

        with pytest.raises(ChildProcessError):
            start_cycle(user)

        cycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()

        assert cycle is not None
        assert mock_celery_task.start_cycle_end_notification_task.called is False
        assert mock_flash.call_count == 1
        mock_flash.assert_called_with('You already have a cycle running!', category='toast-warning')


@patch('app.functions.trigger_relay')
@patch('app.functions.update_energy_consumption')
@patch('app.functions.flash')
def test_stop_cycle(mock_flash, mock_update_consumption, mock_trigger_relay, app):
    """ Testing stop cycle function in normal conditions. """
    with app.test_request_context():
        user = User.query.first()
        cycle = WashingCycle(user_id=user.id, start_timestamp=datetime.datetime.now(), startkwh=12)
        db.session.add(cycle)
        db.session.commit()
        mock_trigger_relay.return_value = 200

        with patch.object(WashingCycle, 'notification_task', return_value='task id') as mock_notification_task:
            stop_cycle(user)
            assert mock_notification_task.terminate.called

        running_cycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
        stopped_cycles = WashingCycle.query.filter(
            WashingCycle.user_id == user.id, WashingCycle.end_timestamp.is_not(None)
        ).all()
        assert running_cycle is None
        assert len(stopped_cycles) == 1
        mock_flash.assert_called_with('Cycle successfully terminated!', category='toast-success')


@patch('app.functions.flash')
def test_stop_cycle_wrong_user(mock_flash, app):
    """ Testing stop cycle function when another user tries to stop a cycle. """
    with app.test_request_context():
        current_user = User.query.filter_by(username='ivan').first()
        active_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(user_id=active_user.id, start_timestamp=datetime.datetime.now())
        db.session.add(cycle)
        db.session.commit()

        with pytest.raises(ChildProcessError):
            stop_cycle(current_user)

        running_cycle = WashingCycle.query.filter_by(end_timestamp=None).first()
        stopped_cycles = WashingCycle.query.filter(
            WashingCycle.user_id == current_user.id, WashingCycle.end_timestamp.is_not(None)
        ).all()
        assert running_cycle is not None
        assert len(stopped_cycles) == 0
        mock_flash.assert_called_with('You do not have a running cycle!', category='toast-warning')


@patch('app.functions.trigger_relay')
@patch('app.functions.flash')
def test_stop_cycle_trigger_fail(mock_flash, mock_trigger_relay, app):
    """ Testing stop cycle function in normal conditions. """
    with app.test_request_context():
        user = User.query.first()
        cycle = WashingCycle(user_id=user.id, start_timestamp=datetime.datetime.now(), startkwh=12)
        db.session.add(cycle)
        db.session.commit()
        mock_trigger_relay.return_value = 500

        with pytest.raises(ChildProcessError):
            stop_cycle(user)

        running_cycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
        stopped_cycles = WashingCycle.query.filter(
            WashingCycle.user_id == user.id, WashingCycle.end_timestamp.is_not(None)
        ).all()
        assert running_cycle is not None
        assert len(stopped_cycles) == 0
        mock_flash.assert_called_with('Request to turn off the relay failed!\nPlease try again!', category='toast-error')


def test_update_cycle_available(app):
    """ Testing the update cycle function when there is no active cycle. """
    with app.test_request_context():
        user = User.query.first()

        result = update_cycle(user)

        assert result['state'] == 'available'
        assert result['id'] is None


def test_update_cycle_active_cycle(app):
    """ Testing the update cycle function when current user has an active cycle. """
    with app.test_request_context():
        user = User.query.first()
        cycle = WashingCycle(user_id=user.id, start_timestamp=datetime.datetime.now())
        db.session.add(cycle)
        db.session.commit()
        db.session.refresh(cycle)

        result = update_cycle(user)

        assert result['state'] == 'running'
        assert result['id'] == cycle.id


def test_update_cycle_washing_machine_busy(app):
    """ Testing the update cycle function when washing machine is busy. """
    with app.test_request_context():
        current_user = User.query.filter_by(username='ivan').first()
        active_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(user_id=active_user.id, start_timestamp=datetime.datetime.now())
        db.session.add(cycle)
        db.session.commit()
        db.session.refresh(cycle)

        result = update_cycle(current_user)
        assert result['state'] == 'unavailable'
        assert result['id'] is None
        assert result['user'] == active_user.first_name


@patch('app.functions.send_push_to_user')
@patch('app.functions.flash')
def test_split_cycle(mock_flash, mock_send_push, app):
    """ Testing the split cycle function when all conditions are satisfied. """
    with app.test_request_context():
        current_user = User.query.filter_by(username='ivan').first()
        other_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(
            user_id=1, startkwh=0, endkwh=2.3, cost=0.46,
            start_timestamp=datetime.datetime.now() - datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now(),
            paid=False
        )
        db.session.add(cycle)
        db.session.commit()
        split_form = SplitCycleForm()
        split_form.cycle_id.data = cycle.id
        split_form.other_users.data = [other_user.id]

        split_cycle(current_user, split_form)
        db.session.refresh(cycle)

        assert len(cycle.splits) > 0
        assert cycle.splits[0].user_id == other_user.id
        assert mock_send_push.called
        assert other_user in mock_send_push.call_args[0]
        mock_flash.assert_called_with('Cycle split successfully, users need to confirm to complete!', category='toast-success')


@patch('app.functions.send_push_to_user')
@patch('app.functions.flash')
def test_split_cycle_not_owned_by_user(mock_flash, mock_send_push, app):
    """Testing the split cycle function when the cycle is not owned by the current user. """
    with app.test_request_context():
        current_user = User.query.filter_by(username='ivan').first()
        other_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(
            user_id=other_user.id, startkwh=0, endkwh=2.3, cost=0.46,
            start_timestamp=datetime.datetime.now() - datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now(),
            paid=False
        )
        db.session.add(cycle)
        db.session.commit()
        split_form = SplitCycleForm()
        split_form.cycle_id.data = cycle.id
        split_form.other_users.data = [other_user.id]

        split_cycle(current_user, split_form)

        assert len(cycle.splits) == 0
        assert mock_send_push.called is False
        mock_flash.assert_called_with('You can only split your own cycles', category='toast-error')


@patch('app.functions.send_push_to_user')
@patch('app.functions.flash')
def test_split_cycle_already_paid(mock_flash, mock_send_push, app):
    """Testing the split cycle function when the cycle is not owned by the current user. """
    with app.test_request_context():
        current_user = User.query.filter_by(username='ivan').first()
        other_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(
            user_id=current_user.id, startkwh=0, endkwh=2.3, cost=0.46,
            start_timestamp=datetime.datetime.now() - datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now(),
            paid=True
        )
        db.session.add(cycle)
        db.session.commit()
        split_form = SplitCycleForm()
        split_form.cycle_id.data = cycle.id
        split_form.other_users.data = [other_user.id]

        split_cycle(current_user, split_form)

        assert len(cycle.splits) == 0
        assert mock_send_push.called is False
        mock_flash.assert_called_with('You cannot split paid cycles', category='toast-error')


@patch('app.functions.send_push_to_user')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_split_cycle_already_paid_split(mock_flash, mock_redirect, mock_send_push, app):
    """ Testing the split cycle function when a split is already paid. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        other_user = User.query.filter_by(username='andrei').first()
        cycle = WashingCycle(
            user_id=current_user.id, startkwh=0, endkwh=2.3, cost=0.46,
            start_timestamp=datetime.datetime.now() - datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now(),
            paid=False
        )
        cycle.splits.append(WashingCycleSplit(cycle_id=cycle.id, user_id=other_user.id, accepted=True, paid=True))
        db.session.add(cycle)
        db.session.commit()
        split_form = SplitCycleForm()
        split_form.cycle_id.data = cycle.id
        split_form.other_users.data = [other_user.id]

        split_cycle(current_user, split_form)

        assert len(cycle.splits) == 1
        assert mock_send_push.called is False
        assert mock_redirect.called
        mock_flash.assert_called_with('You cannot split cycles that have paid splits', category='toast-error')


@patch('app.functions.send_push_to_user')
@patch('app.functions.CeleryTask')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_update_event(mock_flash, mock_redirect, mock_celery_task, mock_send_push, app):
    """ Testing the update schedule event function in normal conditions. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        event = ScheduleEvent(
            timestamp=datetime.datetime.now() - datetime.timedelta(hours=2),
            start_timestamp=datetime.datetime.now() + datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now() + datetime.timedelta(hours=6),
            user_id=current_user.id
        )
        db.session.add(event)
        db.session.commit()
        db.session.refresh(event)

        new_start_timestamp = event.start_timestamp + datetime.timedelta(hours=1)
        new_end_timestamp = event.end_timestamp + datetime.timedelta(hours=1)

        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_update_event(
                event_id=event.id,
                start_timestamp=new_start_timestamp,
                end_timestamp=new_end_timestamp,
                user=current_user
            )
            assert mock_notification_task.terminate.called

        db.session.refresh(event)

        assert event.start_timestamp == new_start_timestamp
        assert event.end_timestamp == new_end_timestamp
        assert mock_celery_task.start_schedule_notification_task.called
        assert mock_send_push.call_count == 1


@patch('app.functions.send_push_to_user')
@patch('app.functions.CeleryTask')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_update_event_invalid_id(mock_flash, mock_redirect, mock_celery_task, mock_send_push, app):
    """ Testing the update schedule event function with invalid event id. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()

        new_start_timestamp = datetime.datetime.now() + datetime.timedelta(hours=1)
        new_end_timestamp = new_start_timestamp + datetime.timedelta(hours=3)

        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_update_event(
                event_id=1,
                start_timestamp=new_start_timestamp,
                end_timestamp=new_end_timestamp,
                user=current_user
            )
            assert not mock_notification_task.terminate.called

        mock_flash.assert_called_with('Event not found', category='toast-error')
        assert mock_redirect.called
        assert not mock_celery_task.start_schedule_notification_task.called
        assert mock_send_push.call_count == 0


@patch('app.functions.send_push_to_user')
@patch('app.functions.CeleryTask')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_update_event_wrong_user(mock_flash, mock_redirect, mock_celery_task, mock_send_push, app):
    """ Testing the update schedule event function with wrong user. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        event_user = User.query.filter_by(username='andrei').first()
        event = ScheduleEvent(
            timestamp=datetime.datetime.now() - datetime.timedelta(hours=2),
            start_timestamp=datetime.datetime.now() + datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now() + datetime.timedelta(hours=6),
            user_id=event_user.id
        )
        db.session.add(event)
        db.session.commit()
        db.session.refresh(event)

        new_start_timestamp = event.start_timestamp + datetime.timedelta(hours=1)
        new_end_timestamp = event.end_timestamp + datetime.timedelta(hours=1)

        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_update_event(
                event_id=event.id,
                start_timestamp=new_start_timestamp,
                end_timestamp=new_end_timestamp,
                user=current_user
            )
            assert not mock_notification_task.terminate.called

        db.session.refresh(event)

        mock_flash.assert_called_with('You can only edit your own events', category='toast-error')
        assert mock_redirect.called
        assert not mock_celery_task.start_schedule_notification_task.called
        assert mock_send_push.call_count == 0


@patch('app.functions.send_push_to_user')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_delete_event(mock_flash, mock_redirect, mock_send_push, app):
    """ Testing the delete schedule event function in normal conditions. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        event = ScheduleEvent(
            timestamp=datetime.datetime.now() - datetime.timedelta(hours=2),
            start_timestamp=datetime.datetime.now() + datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now() + datetime.timedelta(hours=6),
            user_id=current_user.id
        )
        db.session.add(event)
        db.session.commit()
        db.session.refresh(event)

        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_delete_event(event_id=event.id, user=current_user)
            assert mock_notification_task.terminate.called

        assert ScheduleEvent.query.get(event.id) is None
        assert mock_send_push.call_count == 1


@patch('app.functions.send_push_to_user')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_delete_event_invalid_id(mock_flash, mock_redirect, mock_send_push, app):
    """ Testing the delete schedule event function with invalid event id. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        event_id = 1
        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_delete_event(event_id=event_id, user=current_user)
            assert not mock_notification_task.terminate.called

        assert ScheduleEvent.query.get(event_id) is None
        mock_flash.assert_called_with('Event not found', category='toast-error')
        assert mock_redirect.called
        assert mock_send_push.call_count == 0


@patch('app.functions.send_push_to_user')
@patch('app.functions.redirect')
@patch('app.functions.flash')
def test_schedule_delete_event_wrong_user(mock_flash, mock_redirect, mock_send_push, app):
    """ Testing the delete schedule event function in normal conditions. """
    with app.test_request_context('/'):
        current_user = User.query.filter_by(username='ivan').first()
        event_user = User.query.filter_by(username='andrei').first()
        event = ScheduleEvent(
            timestamp=datetime.datetime.now() - datetime.timedelta(hours=2),
            start_timestamp=datetime.datetime.now() + datetime.timedelta(hours=4),
            end_timestamp=datetime.datetime.now() + datetime.timedelta(hours=6),
            user_id=event_user.id
        )
        db.session.add(event)
        db.session.commit()
        db.session.refresh(event)

        with patch.object(ScheduleEvent, 'notification_task', return_value='task id') as mock_notification_task:
            schedule_delete_event(event_id=event.id, user=current_user)
            assert not mock_notification_task.terminate.called

        assert ScheduleEvent.query.get(event.id) is not None
        mock_flash.assert_called_with('You can only delete your own events', category='toast-error')
        assert mock_redirect.called
        assert mock_send_push.call_count == 0
