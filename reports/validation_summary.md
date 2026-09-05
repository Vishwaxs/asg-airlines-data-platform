# Validation rule summary

| rule | table.column | severity | failed | total |
|---|---|---|---|---|
| flight_id_not_null | flights.flight_id | error | 0 | 1020 |
| flight_id_format | flights.flight_id | error | 0 | 1020 |
| flight_route_city_valid | flights.source | error | 0 | 1020 |
| flight_destination_city_valid | flights.destination | error | 0 | 1020 |
| flight_departure_not_null | flights.departure_time | error | 0 | 1020 |
| flight_arrival_not_null | flights.arrival_time | error | 0 | 1020 |
| flight_airline_missing | flights.airline | warning | 41 | 1020 |
| flight_airline_sentinel | flights.airline | warning | 31 | 1020 |
| booking_id_not_null | bookings.booking_id | error | 0 | 1000 |
| booking_id_unique | bookings.booking_id | error | 0 | 1000 |
| booking_status_missing | bookings.status | warning | 45 | 1000 |
| booking_status_sentinel | bookings.status | warning | 30 | 1000 |
| booking_flight_id_referential | bookings.flight_id | error | 0 | 1000 |
| booking_passenger_id_referential | bookings.passenger_id | error | 0 | 1000 |
| booking_passport_format | bookings.passport_number | warning | 0 | 1000 |
| booking_emergency_phone_format | bookings.emergency_contact_phone | warning | 0 | 1000 |
| payment_id_not_null | payments.payment_id | error | 0 | 1000 |
| payment_id_unique | payments.payment_id | error | 0 | 1000 |
| payment_booking_id_referential | payments.booking_id | error | 0 | 1000 |
| payment_amount_missing | payments.amount | warning | 48 | 1000 |
| payment_method_valid | payments.payment_method | warning | 0 | 1000 |
| passenger_id_not_null | passengers.passenger_id | error | 0 | 1039 |
| passenger_last_name_missing | passengers.last_name | warning | 10 | 1039 |
| passenger_phone_format | passengers.phone | warning | 0 | 1039 |
| passenger_gender_valid | passengers.gender | warning | 0 | 1039 |
| passenger_age_range | passengers.age | warning | 0 | 1039 |
