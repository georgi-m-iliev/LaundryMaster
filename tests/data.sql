INSERT INTO users(id, email, username, password, first_name, last_login, active, fs_uniquifier) VALUES(1, 'ivan@test.com', 'ivan', '$2b$12$7XSJWt2rpmHUiGcTEsZpVON.DuyoWqwgYECdSGIPtwg4/OVSMjq46', 'Ivan', NULL, TRUE, '8a512dcdf7434099a3fecfe1f119987a');
INSERT INTO user_settings(id, user_id, terminate_cycle_on_usage, launch_candy_on_cycle_start) VALUES(1, 1, FALSE, TRUE);
INSERT INTO roles(id, name) VALUES (1, 'user'), (2, 'admin'), (3, 'room_owner');
INSERT INTO roles_users(user_id, role_id) VALUES (1, 1);
INSERT INTO washing_machine(currentkwh, costperkwh, public_wash_cost, notification_task_id) VALUES(0, 0.20, 10, NULL);