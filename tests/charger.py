"""Small helper used in tests to obtain an access token from Zaptec's OAuth endpoint.

This helper performs a POST with a form-url-encoded body and returns the parsed
JSON response (or raises on error). Tests should mock the network call where
possible to avoid real HTTP requests.
"""

from smart_charger.zaptec import ZaptecClient

if __name__ == "__main__":
    # Quick local demonstration (won't work without credentials) — don't call in CI.
    try:
        client = ZaptecClient()
        #token_response = client.get_access_token("tobias@terstad.se", "C&0UnfpQ23JGOk")
        #print("Demo run: obtained access token:", token_response.access_token)

        client.access_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjgzMzZiYWU3LWM1MDYtNDMyMi1hZjUwLWIxYjc1MTdjZDA3YiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkuemFwdGVjLmNvbSJdLCJjbGllbnRfaWQiOiI1NmVhMWNjNi0yMjEzLTRmYmUtYjM1Ni01NDIyZjkzOGM4NDAiLCJleHAiOjE3Njg4MjQyNDYsImV4dCI6eyJlbWFpbCI6InRvYmlhc0B0ZXJzdGFkLnNlIiwiemFwQ2xvdWRVc2VySWQiOiI5NzNmYWRjYi0zOTAyLTRjNTEtYTEwOS0xNmYzNWU1ZWMxMzgifSwiaWF0IjoxNzY4NzM3ODQ2LCJpc3MiOiJodHRwczovL2F1dGguemFwdGVjLmNvbSIsImp0aSI6ImE1NGZjOGEwLTY2ZWMtNDUxZS1hYzE2LWU5ZTY0OWUxNWJmMSIsIm5iZiI6MTc2ODczNzg0Niwic2NwIjpbXSwic3ViIjoiNWQ1ZDgyNTctNWExYy00MWNlLTlhYTktMTdjMDhiZDI4YmJiIn0.iSnyNz7bQxi4A2creGg7Tzy88M0UG2Z81R9Hs1eMHrGsZrqmxgg0H7okrf-Dfq0dsw0UtUrNRhXzbthmioBLIPqWYgeVFhwAtCBhYPpt6NZi7VtqWtjwsd-q-j13lHqXDMsJsg4dTsK9zkl8xmm4WtFNt7zVJsid12BXRlyoQGbZZd1i7BB2peE95b_JK_Hy-di8OJhyAPGygdNf9WWe3YXsWfzkeySsPxmEbyTk0N2IGssx8MCA866bRP_SP6n5hq2W3W7HdPZRV_CUQjxHUJatYcoiFIQBAkISE9zPac8zldueILbrN10woGe1O8-7YrxkWraN73smNzZx_OgWvdg6yKiap-X7dC14B61_z_5h7aV0_ksLdM2yxNktuQvgy7pOvMRsr3s-Sbz-N62xpVlMmJ_I0f_TeiL3QPLVC9Jx2rPOf3YdL0p_eDR9N_KpEo1Pp0rUdzwF-X401QyRkLeQsZA7F_b-1psst4dxoEDVgv50GRoToyNcXgAvjnV6QbIX7CQ6_qvJw7hzRHNW4rItPXi-5K63Ghj6YADEkZXbfSWdF70oI3m-VC3uV6FgncloDUofjHmqWsAmtSnBAKC9k1CgZKOPpWvvy6MaCN8c24dq2dewYNA93tIyWVYR4ygYgydrxmndLtdo-6uYiiE7f1aFHI3C4IFEPbz7F9w"
        installations = client.get_installations()
        print("Demo run: obtained installations:", installations)
        print(installations.Data[0].Name)
        print(installations.Data[0].Id)
        print(installations.Data[0].AvailableCurrent)

        #client.update_installation(installations.Data[0].Id, 10.0)

        charger_id = "bdd66bf8-2f1f-4488-9152-1f02ff988538"
        res = client.get_charger_details(charger_id)
        print(res)
        #client.update_charger(charger_id, 10.0)








    except Exception as exc:
        print("Demo run: not executed -", exc)
