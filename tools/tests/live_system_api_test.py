# ~/tools/tests/live_system_api_test.py
# This test file is designed to be run in a live system environment where the database and Redis services are already running.

"""
Current endpoints and how they run in order:
- GET '/' Root endpoint, checks if the API is online.
- POST '/api-auth-test' Auth test endpoint, checks if the API authentication is working.
- POST '/api/db/users/create' User creation endpoint, creates a new user in the database.
- GET '/api/db/users/list' User listing endpoint, retrieves a list of all users in the database.
- POST '/login-auth-test' Login test endpoint, checks if the login authentication is working.
- POST '/cookie-auth-test' Cookie auth test endpoint, checks if the cookie authentication is working.
- PATCH'/api/db/users/password' Password update endpoint, updates the password for a user in the database.
- POST '/login-auth-test' Login test endpoint, checks if the login authentication is working after password update. (Intentional wrong password to test failure)
- POST '/cookie-auth-test' Cookie auth test endpoint, checks if the cookie authentication is working after password update. (Token should be invalidated)
- POST '/login-auth-test' Login test endpoint, checks if the login authentication is working after password update. (Correct password to test success)
"""
