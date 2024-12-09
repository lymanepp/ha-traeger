"""
Library to interact with traeger grills

Copyright 2020 by Keith Baker All rights reserved.
This file is part of the traeger python library,
and is released under the "GNU GENERAL PUBLIC LICENSE Version 2".
Please see the LICENSE file that should have been included as part of this package.
"""

import asyncio
import datetime
import json
import logging
import socket
import ssl
import threading
import time
from typing import Any, Callable, Dict, List, cast
from urllib.parse import urlparse
import uuid

import aiohttp
import async_timeout
from dacite import Config, from_dict
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
import paho.mqtt.client as mqtt

from .model import Acc, Details, Device, Features, GrillMode, Limits, Settings, Status, Thing, User

AccessoryUpdateCallback = Callable[[], None]

CLIENT_ID = "2fuohjtqv1e63dckp5v84rau0j"
TIMEOUT = 60

_LOGGER: logging.Logger = logging.getLogger(__package__)


class traeger:  # pylint: disable=invalid-name,too-many-instance-attributes,too-many-public-methods
    """Traeger API Wrapper"""

    def __init__(
        self,
        username: str,
        password: str,
        hass: HomeAssistant,
        request_library: aiohttp.ClientSession,
    ):
        self.username = username
        self.password = password
        self.mqtt_uuid = str(uuid.uuid1())
        self.mqtt_thread_running = False
        self.mqtt_thread: threading.Thread | None = None
        self.mqtt_thread_refreshing = False
        self.grills_active = False
        self.grills: List[Thing] = []
        self.hass = hass
        self.loop = hass.loop
        self.task: asyncio.TimerHandle | None = None
        self.mqtt_url = None
        self.mqtt_client: mqtt.Client | None = None
        self.grill_status: Dict[str, Device] = {}
        self.access_token = None
        self.token: str | None = None
        self.token_expires = 0
        self.mqtt_url_expires = time.time()
        self.request = request_library
        self.grill_callbacks: Dict[str, List[AccessoryUpdateCallback]] = {}
        self.mqtt_client_inloop = False
        self.autodisconnect = False

    def __token_remaining(self) -> float:
        """Report remaining token time."""
        return self.token_expires - time.time()

    async def __do_cognito(self) -> Dict[str, Any]:
        """Intial API Login for MQTT Token GEN"""
        t = datetime.datetime.utcnow()
        amzdate = t.strftime("%Y%m%dT%H%M%SZ")
        _LOGGER.info("do_cognito t:%s", t)
        _LOGGER.info("do_cognito amzdate:%s", amzdate)
        _LOGGER.info("do_cognito self.username:%s", self.username)
        _LOGGER.info("do_cognito CLIENT_ID:%s", CLIENT_ID)
        return await self.__api_wrapper(
            "post",
            "https://cognito-idp.us-west-2.amazonaws.com/",
            data={
                "ClientMetadata": {},
                "AuthParameters": {
                    "PASSWORD": self.password,
                    "USERNAME": self.username,
                },
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": CLIENT_ID,
            },
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Date": amzdate,
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
        )

    async def __refresh_token(self) -> None:
        """Refresh Token if expiration is soon."""
        if self.__token_remaining() < 60:
            request_time = time.time()
            response = await self.__do_cognito()
            self.token_expires = response["AuthenticationResult"]["ExpiresIn"] + request_time
            self.token = response["AuthenticationResult"]["IdToken"]

    async def get_user_data(self) -> Dict[str, Any]:
        """Get User Data."""
        await self.__refresh_token()
        assert self.token is not None
        return await self.__api_wrapper(
            "get",
            "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/users/self",
            headers={"authorization": self.token},
        )

    async def __send_command(self, thingName: str, command: str) -> None:
        """
        Send Grill Commands to API.
        Command are via API and not MQTT.
        """
        _LOGGER.debug("Send Command Topic: %s, Send Command: %s", thingName, command)
        await self.__refresh_token()
        assert self.token is not None
        api_url = "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com"
        await self.__api_wrapper(
            "post_raw",
            f"{api_url}/prod/things/{thingName}/commands",
            data={"command": command},
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
                "Accept-Language": "en-us",
                "User-Agent": "Traeger/11 CFNetwork/1209 Darwin/20.2.0",
            },
        )

    async def __update_state(self, thingName: str) -> None:
        """Update State"""
        await self.__send_command(thingName, "90")

    async def set_temperature(self, thingName: str, temp: int) -> None:
        """Set Grill Temp Setpoint"""
        await self.__send_command(thingName, f"11,{temp}")

    async def set_probe_temperature(self, thingName: str, temp: int) -> None:
        """Set Probe Temp Setpoint"""
        await self.__send_command(thingName, f"14,{temp}")

    async def set_switch(self, thingName: str, switchval: int) -> None:
        """Set Binary Switch"""
        await self.__send_command(thingName, str(switchval))

    async def shutdown_grill(self, thingName: str) -> None:
        """Request Grill Shutdown"""
        await self.__send_command(thingName, "17")

    async def set_timer_sec(self, thingName: str, time_s: int) -> None:
        """Set Timer in Seconds"""
        await self.__send_command(thingName, f"12,{time_s:05d}")

    async def reset_timer(self, thingName: str) -> None:
        """Reset Timer"""
        await self.__send_command(thingName, "13")

    async def __update_grills(self) -> None:
        """Get an update of available grills"""
        data = await self.get_user_data()
        user = from_dict(User, data)
        self.grills = user.things

    def get_grills(self) -> List[Thing]:
        """Get Grills from Class."""
        return self.grills

    def set_callback_for_grill(self, grill_id: str, callback: AccessoryUpdateCallback) -> None:
        """Add to grill callbacks"""
        self.grill_callbacks.get(grill_id, []).append(callback)

    async def grill_callback(self, grill_id: str) -> None:
        """Do Grill Callbacks"""
        if grill_id in self.grill_callbacks:
            for callback in self.grill_callbacks[grill_id]:
                callback()

    def __mqtt_url_remaining(self) -> float:
        """Available MQTT time left."""
        return self.mqtt_url_expires - time.time()

    async def __refresh_mqtt_url(self) -> None:
        """Update MQTT Token"""
        await self.__refresh_token()
        assert self.token is not None
        if self.__mqtt_url_remaining() < 60:
            try:
                mqtt_request_time = time.time()
                myjson = await self.__api_wrapper(
                    "post",
                    "https://1ywgyc65d1.execute-api.us-west-2.amazonaws.com/prod/mqtt-connections",
                    headers={"Authorization": self.token},
                )
                self.mqtt_url_expires = myjson["expirationSeconds"] + mqtt_request_time
                self.mqtt_url = myjson["signedUrl"]
            except KeyError as exception:
                _LOGGER.error("Key Error Failed to Parse MQTT URL %s - %s", myjson, exception)
            except Exception as exception:  # pylint: disable=broad-except
                _LOGGER.error("Other Error Failed to Parse MQTT URL %s - %s", myjson, exception)
        _LOGGER.debug("MQTT URL:%s Expires @:%s", self.mqtt_url, self.mqtt_url_expires)

    def mqtt_connect_func(self) -> None:
        """
        MQTT Thread Function.
        Anything called from self.mqtt_client is not async and needs to be thread safe.
        """
        if self.mqtt_client is not None:
            _LOGGER.debug("Start MQTT Loop Forever")
            while self.mqtt_thread_running:
                self.mqtt_client_inloop = True
                self.mqtt_client.loop_forever()
                self.mqtt_client_inloop = False
                while (
                    self.__mqtt_url_remaining() < 60 or self.mqtt_thread_refreshing
                ) and self.mqtt_thread_running:
                    time.sleep(1)
        _LOGGER.debug("Should be the end of the thread.")

    async def __get_mqtt_client(self) -> None:
        """Setup the MQTT Client and run in a thread."""
        await self.__refresh_mqtt_url()
        if self.mqtt_client is not None:
            _LOGGER.debug("ReInit Client")
        else:
            self.mqtt_client = mqtt.Client(transport="websockets")
            # self.mqtt_client.on_log = self.mqtt_onlog
            # logging passed via enable_logger this would be redundant.
            self.mqtt_client.on_connect = self.mqtt_onconnect
            self.mqtt_client.on_connect_fail = self.mqtt_onconnectfail
            self.mqtt_client.on_subscribe = self.mqtt_onsubscribe
            self.mqtt_client.on_message = self.mqtt_onmessage
            if _LOGGER.level <= 10:  # Add these callbacks only if our logging is Debug or less.
                self.mqtt_client.enable_logger(_LOGGER)
                self.mqtt_client.on_publish = self.mqtt_onpublish  # We dont Publish to MQTT
                self.mqtt_client.on_unsubscribe = self.mqtt_onunsubscribe
                self.mqtt_client.on_disconnect = self.mqtt_ondisconnect
                self.mqtt_client.on_socket_open = self.mqtt_onsocketopen
                self.mqtt_client.on_socket_close = self.mqtt_onsocketclose
                self.mqtt_client.on_socket_register_write = self.mqtt_onsocketregisterwrite
                self.mqtt_client.on_socket_unregister_write = self.mqtt_onsocketunregisterwrite
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.mqtt_client.tls_set_context(context)
            self.mqtt_client.reconnect_delay_set(min_delay=10, max_delay=160)
        mqtt_parts = urlparse(self.mqtt_url)
        headers = {
            "Host": "{0:s}".format(
                mqtt_parts.netloc.decode()
            ),  # pylint: disable=consider-using-f-string
        }
        self.mqtt_client.ws_set_options(
            path=f"{mqtt_parts.path.decode()}?{mqtt_parts.query.decode()}", headers=headers
        )
        _LOGGER.info("Thread Active Count:%s", threading.active_count())
        self.mqtt_client.connect(mqtt_parts.netloc, 443, keepalive=300)
        if self.mqtt_thread_running is False:
            self.mqtt_thread = threading.Thread(target=self.mqtt_connect_func)
            self.mqtt_thread_running = True
            self.mqtt_thread.start()

    # ===========================Paho MQTT Functions=====================================================

    def mqtt_onlog(self, client: mqtt.Client, userdata: Any, level: int, buf: str) -> None:
        """MQTT Thread on_log"""
        _LOGGER.debug(
            "OnLog Callback. Client:%s userdata:%s level:%s buf:%s", client, userdata, level, buf
        )

    def mqtt_onconnect(
        self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int
    ) -> None:  # pylint: disable=unused-argument
        """MQTT Thread on_connect"""
        _LOGGER.info("Grill Connected")
        for grill in self.grills:
            grill_id = grill.thingName
            if grill_id in self.grill_status:
                del self.grill_status[grill_id]
            client.subscribe((f"prod/thing/update/{grill_id}", 1))

    def mqtt_onconnectfail(self, client: mqtt.Client, userdata: Any) -> None:
        """MQTT Thread on_connect_fail"""
        _LOGGER.debug("Connect Fail Callback. Client:%s userdata:%s", client, userdata)
        _LOGGER.warning("Grill Connect Failed! MQTT Client Kill.")
        asyncio.run_coroutine_threadsafe(
            self.kill(), self.loop
        )  # Shutdown if we arn't getting anywhere.

    def mqtt_onsubscribe(
        self, client: mqtt.Client, userdata: Any, mid: int, granted_qos: List[int]
    ) -> None:
        """MQTT Thread on_subscribe"""
        _LOGGER.debug(
            "OnSubscribe Callback. Client:%s userdata:%s mid:%s granted_qos:%s",
            client,
            userdata,
            mid,
            granted_qos,
        )

        for grill in self.grills:
            grill_id = grill.thingName
            if grill_id in self.grill_status:
                del self.grill_status[grill_id]
            asyncio.run_coroutine_threadsafe(self.__update_state(grill_id), self.loop)

    def mqtt_onmessage(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:  # pylint: disable=unused-argument
        """MQTT Thread on_message"""
        _LOGGER.debug(
            "grill_message: message.topic = %s, message.payload = %s",
            message.topic,
            message.payload,
        )
        _LOGGER.info(
            "Token Time Remaining:%s MQTT Time Remaining:%s",
            self.__token_remaining(),
            self.__mqtt_url_remaining(),
        )
        if message.topic.startswith("prod/thing/update/"):
            grill_id = message.topic[len("prod/thing/update/") :]
            data = json.loads(message.payload)
            self.grill_status[grill_id] = from_dict(
                data_class=Device, data=data, config=Config(cast=[GrillMode])
            )
            asyncio.run_coroutine_threadsafe(self.grill_callback(grill_id), self.loop)
            if self.grills_active is False:  # Go see if any grills are doing work.
                for grill in self.grills:  # If nobody is working next MQTT refresh
                    grill_id = grill.thingName  # It'll call kill.
                    state = self.get_state_for_device(grill_id)
                    if state is None:
                        return
                    if state.connected:
                        if 4 <= state.system_status <= 8:
                            self.grills_active = True

    def mqtt_onpublish(self, client: mqtt.Client, userdata: Any, mid: int) -> None:
        """MQTT Thread on_publish"""
        _LOGGER.debug("OnPublish Callback. Client:%s userdata:%s mid:%s", client, userdata, mid)

    def mqtt_onunsubscribe(self, client: mqtt.Client, userdata: Any, mid: int) -> None:
        """MQTT Thread on_unsubscribe"""
        _LOGGER.debug("OnUnsubscribe Callback. Client:%s userdata:%s mid:%s", client, userdata, mid)

    def mqtt_ondisconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        """MQTT Thread on_undisconnect"""
        _LOGGER.debug("OnDisconnect Callback. Client:%s userdata:%s rc:%s", client, userdata, rc)

    def mqtt_onsocketopen(self, client: mqtt.Client, userdata: Any, sock: socket.socket) -> None:
        """MQTT Thread on_socketopen"""
        _LOGGER.debug("Sock.Open.Report...Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketclose(self, client: mqtt.Client, userdata: Any, sock: socket.socket) -> None:
        """MQTT Thread on_socketclose"""
        _LOGGER.debug("Sock.Clse.Report...Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketregisterwrite(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """MQTT Thread on_socketregwrite"""
        _LOGGER.debug("Sock.Regi.Write....Client: %s UserData: %s Sock: %s", client, userdata, sock)

    def mqtt_onsocketunregisterwrite(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """MQTT Thread on_socketunregwrite"""
        _LOGGER.debug("Sock.UnRg.Write....Client: %s UserData: %s Sock: %s", client, userdata, sock)

    # ===========================/Paho MQTT Functions===================================================

    def get_state_for_device(self, thingName: str) -> Status | None:
        """Get specifics of status."""
        return self.grill_status[thingName].status if thingName in self.grill_status else None

    def get_details_for_device(self, thingName: str) -> Details | None:
        """Get specifics of details."""
        return self.grill_status[thingName].details if thingName in self.grill_status else None

    def get_limits_for_device(self, thingName: str) -> Limits | None:
        """Get specifics of limits."""
        return self.grill_status[thingName].limits if thingName in self.grill_status else None

    def get_settings_for_device(self, thingName: str) -> Settings | None:
        """Get specifics of settings."""
        return self.grill_status[thingName].settings if thingName in self.grill_status else None

    def get_features_for_device(self, thingName: str) -> Features | None:
        """Get specifics of features."""
        return self.grill_status[thingName].features if thingName in self.grill_status else None

    def get_cloudconnect(self, thingName: str) -> bool:
        """Indicate whether MQTT is connected."""
        return thingName in self.grill_status and self.mqtt_thread_running

    def get_units_for_device(self, thingName: str) -> UnitOfTemperature:
        """Parse what units the grill is operating in."""
        state = self.get_state_for_device(thingName)
        return (
            UnitOfTemperature.CELSIUS
            if state and state.units == 0
            else UnitOfTemperature.FAHRENHEIT
        )

    def get_details_for_accessory(self, thingName: str, accessory_id: str) -> Acc | None:
        """Get Details for Probes"""
        if state := self.get_state_for_device(thingName):
            for accessory in state.acc:
                if accessory.uuid == accessory_id:
                    return accessory
        return None

    async def start(self, delay: float) -> None:
        """
        This is the entry point to start MQTT connect.
        It does have a delay before doing MQTT connect to
        allow HA to finish starting up before lauching threads.
        """
        await self.__update_grills()
        self.grills_active = True
        _LOGGER.info("Call_Later in: %s seconds.", delay)
        self.task = self.loop.call_later(delay, self.__syncmain)

    def __syncmain(self) -> None:
        """
        Small wrapper to switch from the call_later def back to the async loop
        """
        _LOGGER.debug("@Call_Later SyncMain CreatingTask for async Main.")
        self.hass.async_create_task(self.__main())

    async def __main(self) -> None:
        """This is the loop that keeps the tokens updated."""
        _LOGGER.debug("Current Main Loop Time: %s", time.time())
        _LOGGER.debug(
            "MQTT Logger Token Time Remaining:%s MQTT Time Remaining:%s",
            self.__token_remaining(),
            self.__mqtt_url_remaining(),
        )
        if self.__mqtt_url_remaining() < 60:
            self.mqtt_thread_refreshing = True
            if self.mqtt_thread_running and self.mqtt_client is not None:
                self.mqtt_client.disconnect()
                self.mqtt_client = None
            await self.__get_mqtt_client()
            self.mqtt_thread_refreshing = False
        _LOGGER.debug("Call_Later @: %s", self.mqtt_url_expires)
        delay = max(self.__mqtt_url_remaining(), 30)
        self.task = self.loop.call_later(delay, self.__syncmain)

    async def kill(self) -> None:
        """This terminates the main loop and shutsdown the thread."""
        if self.mqtt_thread_running:
            if self.task is not None:
                _LOGGER.info("Killing Task")
                _LOGGER.debug("Task Info: %s", self.task)
                self.task.cancel()
                _LOGGER.debug(
                    "Task Info: %s TaskCancelled Status: %s", self.task, self.task.cancelled()
                )
                self.task = None
            self.mqtt_thread_running = False
            if self.mqtt_client is not None:
                self.mqtt_client.disconnect()
                while self.mqtt_client_inloop:  # Wait for disconnect to finish
                    await asyncio.sleep(0.25)
            self.mqtt_url_expires = time.time()
            # Mark the grill(s) disconnected so they report unavail.
            for grill in self.grills:
                # Also hit the callbacks to update HA
                grill_id = grill.thingName
                self.grill_status[grill_id].status.connected = False
                await self.grill_callback(grill_id)
        else:
            _LOGGER.info("Task Already Dead")

    # pylint: disable=dangerous-default-value
    async def __api_wrapper(
        self, method: str, url: str, data: Dict[str, Any] = {}, headers: Dict[str, str] = {}
    ) -> Dict[str, Any]:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(TIMEOUT):
                if method == "get":
                    response = await self.request.get(url, headers=headers)
                    bytes = await response.read()
                    return cast(Dict[str, Any], json.loads(bytes))

                if method == "post_raw":
                    await self.request.post(url, headers=headers, json=data)
                    return {}

                if method == "post":
                    response = await self.request.post(url, headers=headers, json=data)
                    bytes = await response.read()
                    return cast(Dict[str, Any], json.loads(bytes))

        except asyncio.TimeoutError as exception:
            _LOGGER.error(f"Timeout error fetching information from {url} - {exception}")
        except aiohttp.ClientError as exception:
            _LOGGER.error(f"Error fetching information from {url} - {exception}")
        except (KeyError, TypeError) as exception:
            _LOGGER.error(f"Error parsing information from {url} - {exception}")
        except socket.gaierror as exception:
            _LOGGER.error(f"Error fetching information from {url} - {exception}")
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error(f"Unexpected error fetching data from {url} - {exception}")

        return {}
