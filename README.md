# yesh_mishak

כל הסכמות שצריך להטמיע  ב DB כל טבלה והקטגוריות שבה מצורפות מתחת

users

id, name, phone_number, created_at, last_active

fields

id, name, lat, lng, sport_type (football/basketball/both), surface_type, has_nets, has_water, opening_hours, status (open/closed/renovation), verified, added_by, created_at, notes, image_url

games

id, field_id, created_by, sport_type (football/basketball), players_present, status (active/finished), age_note, started_at, expires_at

game_participants

id, game_id, user_id, joined_at

user_notifications

id, user_id, notification_type (radius/city/specific_field), radius_km, city, field_id
