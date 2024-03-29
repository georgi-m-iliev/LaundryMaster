INSERT INTO users(id, email, username, password, first_name, last_login, active, fs_uniquifier) VALUES
    (1, 'ivan@test.com', 'ivan', '$2b$12$7XSJWt2rpmHUiGcTEsZpVON.DuyoWqwgYECdSGIPtwg4/OVSMjq46', 'Ivan', NULL, TRUE, '8a512dcdf7434099a3fecfe1f119987a'),
    (2, 'andrei@test.com', 'andrei', '$2b$12$7XSJWt2rpmHUiGcTEsZpVON.DuyoWqwgYECdSGIPtwg4/OVSMjq46', 'Andrei', NULL, TRUE, '8a512dcdf7414099a3fecfe1f219987a'),
    (3, 'georgi@test.com', 'georgi', '$2b$12$7XSJWt2rpmHUiGcTEsZpVON.DuyoWqwgYECdSGIPtwg4/OVSMjq46', 'Georgi', NULL, TRUE, '8q512dcdf7434099a3fecfe1f119987c');

INSERT INTO user_settings(id, user_id, terminate_cycle_on_usage, launch_candy_on_cycle_start) VALUES(1, 1, FALSE, TRUE);
INSERT INTO roles(id, name) VALUES (1, 'user'), (2, 'admin'), (3, 'room_owner');
INSERT INTO roles_users(user_id, role_id) VALUES (1, 1), (2, 1), (2, 3), (3, 1), (3, 2);
INSERT INTO washing_machine(currentkwh, costperkwh, public_wash_cost, candy_device_id, candy_appliance_id, global_shutdown, require_scheduling) VALUES(17.0599,0.20,10.00,'b461fca47c039e37','52528914-64ef-4fc8-a851-3006b0360639', false, false);
