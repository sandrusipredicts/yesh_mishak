# yesh_mishak

כל הסכמות שצריך להטמיע  ב DB כל טבלה והקטגוריות שבה מצורפות מתחת

users

id, name, phone_number, created_at, last_active

fields

id, name, lat, lng, sport_type (football/basketball/both), surface_type, has_nets, has_water, opening_hours, status (pending/approved/rejected/renovation), verified, added_by, created_at, notes, image_url

games

id, field_id, created_by, sport_type (football/basketball), players_present, max_players, status (open/full/finished/cancelled), age_note, min_age, max_age, started_at, expires_at

game_players

id, game_id, user_id, joined_at

notification_preferences

id, user_id, notification_type (radius/city/specific_field), radius_km, city, field_id, created_at
