from mailtm.server.events import RecieveMessage
from mailtm.core.methods import ServerAuth
from mailtm.server.server import Server


cs = Server(
    server_auth=ServerAuth(
        account_id="663713bb3fa94ea19b0586ac",
        account_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpYXQiOjE3MTQ5MTE4NTcsInJvbGVzIjpbIlJPTEVfVVNFUiJdLCJhZGRyZXNzIjoiOTUxcmVkdW5kYW50QGZ0aGNhcGl0YWwuY29tIiwiaWQiOiI2NjM3MTNiYjNmYTk0ZWExOWIwNTg2YWMiLCJtZXJjdXJlIjp7InN1YnNjcmliZSI6WyIvYWNjb3VudHMvNjYzNzEzYmIzZmE5NGVhMTliMDU4NmFjIl19fQ.Yv3dAEbDWXOHtc7azN_YMTi-G6CQX4huXI80k7H00cvhd0q0KsYD0ArSctytanSLXdW0uChndkbCCCoy-QrzJQ",
    )
)


@cs.subscribe(event=RecieveMessage)
async def event(event: RecieveMessage): ...


cs.run()
