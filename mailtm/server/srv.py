import typing as t
import asyncio
import aiofiles
import datetime
import pathlib

from colorama import Fore
from mailtm.core.methods import ServerAuth, AttachServer
from mailtm.server.events import BaseEvent, NewMessage, DomainChange
from mailtm.abc.modals import Message, Domain
from mailtm.abc.generic import Token
from mailtm.impls.xclient import AsyncMail

default_banner = pathlib.Path("mailtm/server/assets/banner.txt")
ServerSideEvents = t.TypeVar("ServerSideEvents", bound=BaseEvent)


class MailServerBase:
    """
    Base Implementation of a Mail Server.
    ---
    This class provides a basic implementation for a mail server, including internal handlers and dispatchers.
    It is meant to be subclassed into the main usable server, and is not intended for basic usage provided by
    the library.
    """

    def __init__(
        self,
        server_auth: ServerAuth,
        pooling_rate: t.Optional[int],
        banner: t.Optional[bool] = True,
        banner_path: t.Optional[t.Union[pathlib.Path, str]] = default_banner,
        suppress_errors: t.Optional[bool] = False,
        enable_logging: t.Optional[bool] = False
    ) -> None:
        """
        Initializes a new instance of the `MailServerBase` class.

        Args:
            server_auth (ServerAuth): An instance of the `ServerAuth` class containing the server authentication details.
            pooling_rate (Optional[int]): The rate at which the server should pool for new messages.
            banner (Optional[bool], optional): Whether to display a banner upon initialization. Defaults to True.
            banner_path (Optional[Union[Path, str]], optional): The path to the banner file. Defaults to the default banner file.
            suppress_errors (Optional[bool], optional): Whether to suppress errors. Defaults to False.
            enable_logging (Optional[bool], optional): Whether to enable logging. Defaults to False.
            save_output (Optional[bool], optional): Whether to save output. Defaults to False.

        Returns:
            None
        """
        self._banner_enabled = banner
        self._banner_path = banner_path
        self._pooling_rate = pooling_rate
        self._suppress_errors = suppress_errors
        self._logging_enabled = enable_logging
        self.handlers: t.Dict[
            t.Type[BaseEvent],
            list[t.Callable[[BaseEvent], t.Awaitable[None]]],
        ] = {}
        self._server_auth = server_auth
        self._last_msg: list[Message] = []
        self._last_domain: list[Domain] = []
        self.mail_client = AsyncMail(
            account_token=Token(
                id=self._server_auth.account_id,
                token=self._server_auth.account_token,
            )
        )

    def log(
        self,
        message: str,
        severity: t.Literal["INFO", "WARNING", "ERROR"] = "INFO",
    ) -> None:
        if self._logging_enabled is True:
            if severity == "INFO":
                print(
                    Fore.LIGHTGREEN_EX
                    + f"[+]{Fore.RESET} At {datetime.datetime.now()} "
                    + message
                )
            if self._suppress_errors is False:
                if severity == "WARNING":
                    print(
                        Fore.LIGHTYELLOW_EX
                        + f"[!]{Fore.RESET} At {datetime.datetime.now()} "
                        + message
                    )
                elif severity == "ERROR":
                    print(
                        Fore.LIGHTRED_EX
                        + f"[-]{Fore.RESET} At {datetime.datetime.now()} "
                        + message
                    )
            else:
                print(
                    Fore.WHITE
                    + f"[?] Unrecognized severity: {datetime.datetime.now()} "
                    + message
                )

    def subscribe(
        self, event_type: t.Type[BaseEvent]
    ) -> t.Callable[
        [t.Callable[[ServerSideEvents], t.Awaitable[None]]],
        t.Callable[[ServerSideEvents], t.Awaitable[None]],
    ]:
        """
        Decorator to subscribe a function to handle server events.

        Args:
            event_type (Type[BaseEvent]): The type of event to subscribe to.

        Returns:
            Callable: The decorated function.
        """

        def decorator(
            handler_func: t.Callable[[ServerSideEvents], t.Awaitable[None]],
        ) -> t.Callable[[ServerSideEvents], t.Awaitable[None]]:
            if event_type not in self.handlers:
                self.handlers[event_type] = []
            self.handlers[event_type].append(handler_func)  # type: ignore
            return handler_func

        return decorator

    def on_new_message(
        self, func: t.Callable[[NewMessage], t.Awaitable[None]]
    ):
        if NewMessage not in self.handlers:
            self.handlers[NewMessage] = []
        self.handlers[NewMessage].append(func)  # type: ignore
        return func

    def on_new_domain(
        self, func: t.Callable[[DomainChange], t.Awaitable[None]]
    ):
        if DomainChange not in self.handlers:
            self.handlers[DomainChange] = []
        self.handlers[DomainChange].append(func)  # type: ignore
        return func

    async def dispatch(self, event: BaseEvent) -> None:
        """
        Asynchronously dispatches the given event to the appropriate handlers.

        Args:
            self: The MailServerBase instance.
            event (BaseEvent): The event to dispatch.

        Returns:
            None
        """
        for handler in self.handlers.get(type(event), []):
            await handler(event)

    async def _check_for_new_messages(self) -> None:
        """
        Asynchronously checks for new messages by retrieving message information from the mail client.
        If new messages are detected, triggers a NewMessage event with the new message details.

        Returns:
            None
        """
        msg_view = await self.mail_client.get_messages()
        if msg_view and msg_view.messages:
            if (
                not self._last_msg
                or self._last_msg[0].id != msg_view.messages[0].id
            ):
                if self._last_msg:
                    self._last_msg[0] = msg_view.messages[0]
                else:
                    self._last_msg.append(msg_view.messages[0])
                new_message_event = NewMessage(
                    "NewMessage",
                    client=self.mail_client,
                    _server=AttachServer(self),
                    new_message=msg_view.messages[0],
                )
                await self.dispatch(new_message_event)
                self.log(message=f"RECIEVED new message from: {msg_view.messages[0].message_from.address}") #type: ignore
        return None

    async def _check_for_new_domain(self) -> t.Optional[Domain]:
        """
        Asynchronously checks for a new domain by retrieving domain information from the mail client.
        If a new domain is detected, triggers a DomainChange event with the new domain details.

        Returns:
            t.Optional[Domain]: The newly detected domain, if any.
        """
        domain_view = await self.mail_client.get_domains()
        if domain_view and domain_view.domains:
            if (
                not self._last_domain
                or self._last_domain[0].id != domain_view.domains[0].id
            ):
                if self._last_domain:
                    self._last_domain[0] = domain_view.domains[0]
                else:
                    self._last_domain.append(domain_view.domains[0])
                new_domain_event = DomainChange(
                    event="DomainChange",
                    client=self.mail_client,
                    _server=AttachServer(self),
                    new_domain=domain_view.domains[0],
                )
                await self.dispatch(new_domain_event)
                self.log(message=f"Domain Changed: {domain_view.domains[0].domain_name}", severity="WARNING")
    async def _banner(self) -> None:
        """
        Asynchronously prints a banner from the specified file path if it exists.
        The banner is formatted with the current time and date, and includes color codes for different parts of the banner.
        If an exception occurs while reading or printing the banner, it is logged.

        :return: None
        """
        if self._banner_path is not None:
            try:
                async with aiofiles.open(
                    self._banner_path, "r", encoding="utf-8"
                ) as f:
                    text = await f.read()
                    details = text.format(
                        time=datetime.datetime.now(),
                        date=f"{datetime.date.today()}",
                        mail=Fore.CYAN,
                        reset=Fore.RESET,
                        sdk=Fore.MAGENTA,
                        ssb=Fore.GREEN,
                        version=Fore.LIGHTBLUE_EX,
                        info=Fore.LIGHTMAGENTA_EX,
                        issues=Fore.RED,
                        warning=Fore.LIGHTYELLOW_EX,
                        dateandtime=Fore.GREEN,
                    )
                    print(details)
            except Exception as e:
                self.log(
                    f"Exception while printing banner:\n{Fore.LIGHTWHITE_EX+str(e)+Fore.RESET}"
                )

    async def runner(self) -> None:
        """
        Asynchronously runs the server logic.

        This function is responsible for executing the main server logic. It starts a session and continuously polls the API for new events. When a difference is detected, the corresponding event is dispatched. The function runs in an infinite loop until it is interrupted by a keyboard interrupt.

        Parameters:
            None

        Returns:
            None

        Raises:
            Exception: If no events have been subscribed to.
        """
        if self._banner_enabled is True:
            await self._banner()
        try:
            self.log(
                message="Server-> Session Started: "
                + datetime.datetime.now().strftime("%H:%M:%S")
            )
            self.log(
                message="Server-> Pooling rate: " + str(self._pooling_rate)
            )
            self.log(
                message="Server-> Logging enabled: "
                + str(self._logging_enabled)
            )
            self.log(
                message="Server-> Banner enabled: " + str(self._banner_enabled)
            )
            self.log(
                message="Server-> Subscribed events: "
                + str(len(self.handlers.keys()))
            )
            while True:
                await asyncio.sleep(self._pooling_rate or 1)
                if NewMessage in self.handlers:
                    await self._check_for_new_messages()
                if DomainChange in self.handlers:
                    await self._check_for_new_domain()
                if not self.handlers:
                    await self.mail_client.close()
                    raise Exception(
                        "It seems like you have not subscribed to any events."
                    )
        except Exception as e:
            await self.mail_client.close()
            self.log(
                message=f"Exception while running server:\n{Fore.LIGHTWHITE_EX+str(e)+Fore.RESET}"
            )

    def run(self)->None:
        """
        Executes the main server logic by running the event runner within asyncio event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.runner())
            loop.close()
        except KeyboardInterrupt:
            self.log(
                message="Server is closing it's operations. Goodbye!",
                severity="WARNING",
            )
