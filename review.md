# Code Review Report: Smart Charger Application

---

## 1. Security Issues

### 🔴 High Severity

#### 1.1 Logging of Sensitive Data
**File:** `src/smart_charger/secrets.py` (lines 94-96)
```python
logger.info(
    "save_zaptec_token called with token: %s",
    access_token[:50] if access_token else "None",
)
```
**Issue:** Even though only the first 50 characters are logged, partial tokens can still be useful for attackers. The token itself shouldn't be logged at all.

#### 1.2 Hardcoded MQTT Credentials Absent
**File:** `src/smart_charger/tools/mqtt.py` (lines 8-9)
```python
broker = "10.100.0.10"
port = 1883
```
**Issue:** No authentication is configured. While this appears to be a local network tool, production deployments should use authentication.

#### 1.3 API Key in Configuration File Path
**File:** `src/smart_charger/tibber/tariff.py` (line 103)
```python
with open(os.path.expanduser("~/.ctek/config.yaml"), "r") as f:
```
**Issue:** Hardcoded path to config file. API key is read from a YAML file but the path is not configurable.

---

### 🟡 Medium Severity

#### 1.4 Secrets File Path is Predictable
**File:** `src/smart_charger/secrets.py` (line 9)
```python
SECRETS_PATH = Path.home() / ".config" / "smart-charger" / "secrets.toml"
```
**Issue:** The secrets file location is predictable. Consider using additional protection mechanisms.

---

## 2. Code Quality & Best Practices

### 🟡 Medium Severity

#### 2.1 Bare Except Clauses
**Files:** Multiple locations
- `src/smart_charger/smartcharger.py` (line 430)
- `src/smart_charger/chargers.py` (lines 142, 155, 168)
- `src/smart_charger/messages.py` (lines 228, 293)
- `src/smart_charger/session.py` (lines 204, 212)
- `src/smart_charger/price_providers.py` (line 66)

**Issue:** Using bare `except Exception:` catches all exceptions including `KeyboardInterrupt` and `SystemExit`. Should catch specific exceptions.

#### 2.2 Incorrect Exception Handling in `stop_charging`
**File:** `src/smart_charger/chargers.py` (lines 155-156, 168-169)
```python
except Exception as e:
    logger.exception("Failed to start charging", e)  # Wrong: 'e' should not be passed as argument
```
**Issue:** `logger.exception()` automatically includes the traceback - passing `e` as an argument is incorrect and will print the exception object as a separate message.

#### 2.3 Unused Variable
**File:** `src/smart_charger/smartcharger.py` (line 93)
```python
self.effect_tariff_stopped_hour: Optional[int] = None
```
**Issue:** This variable is assigned but never read.

---

### 🟢 Low Severity

#### 2.4 Missing Type Hints
**File:** `src/smart_charger/smartcharger.py` (lines 224, 234)
```python
def _on_high_consumption_stop(session):
def _on_high_consumption_start(self, session):
```
**Issue:** Missing type hints for parameters.

#### 2.5 Inconsistent Return Types
**File:** `src/smart_charger/chargers.py` (lines 176-188)
```python
@staticmethod
def map_status(status: str):
```
**Issue:** Missing return type annotation. Returns `ChargerStatus | None`.

#### 2.6 TODO Comments
- `src/smart_charger/smartcharger.py` (line 273): "TODO: Decide if this should also be a status"
- `src/smart_charger/solar_providers.py` (line 98): "TODO: Add min and max current for the charger configuration"

---

## 3. Potential Bugs & Edge Cases

### 🔴 High Severity

#### 3.1 Potential None Reference in `_on_session_start`
**File:** `src/smart_charger/smartcharger.py` (lines 172-174)
```python
session.target_soc = self.config.get_vehicle_config_by_id(
    session.vehicle.id
).target_soc
```
**Issue:** If `get_vehicle_config_by_id` returns `None`, this will raise `AttributeError`. The vehicle config could be missing.

#### 3.2 Session Could Have No Vehicle
**File:** `src/smart_charger/session.py` (lines 65-75)
```python
def get_charger(self, vehicle_id: str, chargers: list[BaseCharger]) -> Optional[BaseCharger]:
    session = self.get_session_by_vehicle(vehicle_id, join=False)
    if session:
        logger.debug("Vehicle %s is connected to charger %s", vehicle_id, session.charger.id)  # Potential None
```
**Issue:** `session.charger` could be `None` if the session exists but charger is not yet connected.

#### 3.3 Null Check Missing in `_on_target_reached`
**File:** `src/smart_charger/smartcharger.py` (lines 212-217)
```python
def _on_target_reached(self, vehicle: VehicleStatus):
    session = self.session_manager.get_session_by_vehicle(vehicle_id=vehicle.id)
    logger.info(f"Target soc {session.target_soc} reached for {vehicle.id}")  # session could be None
```
**Issue:** If no session exists for the vehicle, `session` will be `None` and accessing `.target_soc` will fail.

#### 3.4 Topic Subscription Without Null Check
**File:** `src/smart_charger/messages.py` (lines 184-193)
```python
if msg.topic == self.config.power_consumption_topic:
    self._handle_float_message(msg, self._on_power_consumption_changed)
```
**Issue:** `self.config.power_consumption_topic` could be `None` (it's `Optional[str]`), causing a comparison error.

---

### 🟡 Medium Severity

#### 3.5 Race Condition in `SessionManager.get_session_by_vehicle`
**File:** `src/smart_charger/session.py` (lines 77-94)
```python
def get_session_by_vehicle(self, vehicle_id: str, join=True) -> Optional[ChargingSession]:
    for session in self.current_sessions:
        if session.vehicle and session.vehicle.id == vehicle_id:
            return session

    if join:
        for session in self.current_sessions:
            if session.vehicle is None:  # Could be joined by another thread between loops
```
**Issue:** Not thread-safe. Another thread could join a vehicle to a session between the two loops.

#### 3.6 Hardcoded Voltage Value
**File:** `src/smart_charger/solar_providers.py` (line 94)
```python
voltage = 230
```
**Issue:** Voltage is hardcoded. Should be configurable (different countries have different voltages).

#### 3.7 Division by Zero Potential
**File:** `src/smart_charger/planner.py` (line 33)
```python
hours = (self.stop_time - self.start_time).total_seconds() / 3600
```
**Issue:** If `stop_time` is before `start_time`, this will produce negative energy.

#### 3.8 Missing Validation for SOC Range
**File:** `src/smart_charger/messages.py` (lines 164-177)
```python
vehicle_status.soc = int(msg.payload.decode())
```
**Issue:** No validation that SOC is within valid range (0-100). Invalid values will be accepted.

---

## 4. Performance Concerns

### 🟢 Low Severity

#### 4.1 Inefficient String Concatenation in Logging
**File:** `src/smart_charger/session.py` (lines 131, 141, 163, 172)
```python
logger.info(f"Created session: \n{session}")
```
**Issue:** Using f-strings with complex objects (like Pydantic models) triggers `__str__` conversion even when logging level is higher than INFO.

#### 4.2 Repeated Dictionary Lookups
**File:** `src/smart_charger/session.py` (lines 86-91)
```python
for session in self.current_sessions:
    if session.vehicle is None:
        logger.info("Joining vehicle %s to existing session with charger %s", vehicle_id, session.charger.id)
```
**Issue:** Could fail if `session.charger` is None (only `session.vehicle` is checked).

#### 4.3 Price Provider Called Without Caching
**File:** `src/smart_charger/planner.py` (lines 487-492)
```python
for cand in candidates:
    price = self.price_provider.price_at(cand.dt) if self.price_provider else 0.0
```
**Issue:** `price_at` is called for every candidate hour. If this involves API calls, there's no batching or caching.

---

## 5. Code Readability & Maintainability

### 🟡 Medium Severity

#### 5.1 Unused Imports
**File:** `src/smart_charger/solar_providers.py` (line 6)
```python
import json
```
**Issue:** Import is unused.

#### 5.2 Duplicated Code in `messages.py`
**Files:** `src/smart_charger/messages.py` (MessageListener and MessageSender)

Both classes have very similar `connect_mqtt()`, `_schedule_reconnect()`, and `_do_reconnect()` methods. This should be refactored into a shared base class or utility function.

#### 5.3 Complex Method in `SimpleHourPlanner`
**File:** `src/smart_charger/planner.py` (lines 263-356)

The `plan_charging` method is 94 lines long with complex logic. Should be broken into smaller helper methods.

#### 5.4 Inconsistent Naming in `secrets.py`
**File:** `src/smart_charger/secrets.py` (lines 59-90)

Some properties return empty string on missing values (`or ""`), while others may return `None`. This inconsistency can cause issues downstream.

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 High  | 7     |
| 🟡 Medium| 14    |
| 🟢 Low   | 7     |

**Critical fixes needed:**
1. Add null checks for session/vehicle/charger references before accessing their properties
2. Fix the logging of sensitive data (tokens)
3. Add validation for SOC values
4. Fix incorrect exception handling in charger methods

The codebase is generally well-structured with good separation of concerns. The main areas needing attention are null-safety and proper error handling.

---

# Detailed Null Safety Improvement Plan

## 1. smartcharger.py

### Issue 1.1: `_on_session_start` (lines 160-176)
**Current code:**
```python
logger.info(
    f"Session started/updated: {session.id} (vehicle={session.vehicle.id} charger={session.charger.id})"
)
status = session.charger.get_status()
# ...
session.target_soc = self.config.get_vehicle_config_by_id(
    session.vehicle.id
).target_soc
```

**Fix:** Add null checks for `session.vehicle`, `session.charger`, and the return value of `get_vehicle_config_by_id`:
```python
if session.vehicle and session.charger:
    logger.info(
        f"Session started/updated: {session.id} (vehicle={session.vehicle.id} charger={session.charger.id})"
    )
    status = session.charger.get_status()
    # ...

if session.vehicle:
    vehicle_config = self.config.get_vehicle_config_by_id(session.vehicle.id)
    if vehicle_config:
        session.target_soc = vehicle_config.target_soc
        session.plan = self.planner.plan_charging(session.vehicle)
```

### Issue 1.2: `_on_target_reached` (lines 212-217)
**Current code:**
```python
def _on_target_reached(self, vehicle: VehicleStatus):
    session = self.session_manager.get_session_by_vehicle(vehicle_id=vehicle.id)
    logger.info(f"Target soc {session.target_soc} reached for {vehicle.id}")
    status = session.charger.get_status()
```

**Fix:** Add null check for session:
```python
def _on_target_reached(self, vehicle: VehicleStatus):
    session = self.session_manager.get_session_by_vehicle(vehicle_id=vehicle.id)
    if not session:
        logger.warning(f"No session found for vehicle {vehicle.id}")
        return
    logger.info(f"Target soc {session.target_soc} reached for {vehicle.id}")
    if session.charger:
        status = session.charger.get_status()
        if status == OperatingMode.Connected_Charging:
            session.charger.stop_charging()
```

### Issue 1.3: `_on_session_stop` (lines 183-190)
**Current code:**
```python
vehicle = SessionManager.get_vehicle_status_by_id(
    session.vehicle.id, self.vehicles
)
# ...
charger = session.charger
```

**Fix:** Add null checks:
```python
if session.vehicle:
    vehicle = SessionManager.get_vehicle_status_by_id(
        session.vehicle.id, self.vehicles
    )
    if vehicle:
        vehicle.connected = False
charger = session.charger
if charger:
    charger.status = ChargerStatus.DISCONNECTED
```

### Issue 1.4: `_on_charge_start` and `_on_charge_stop` (lines 195-210)
**Current code:**
```python
status = session.charger.get_status()
# ...
session.charger.start_charging()
session.charger.set_current(new_charging_step.current)
```

**Fix:** Add null check for charger:
```python
if session.charger:
    status = session.charger.get_status()
    if status in [...]:
        session.charger.start_charging()
    session.charger.set_current(new_charging_step.current)
```

### Issue 1.5: `_on_high_consumption_stop` (lines 224-231)
**Current code:**
```python
session.charger.status = ChargerStatus.PAUSED
session.charger.reason = ChargerReason.PAUSED_HIGH_LOAD
session.charger.current = 0
session.charger.stop_charging()
```

**Fix:** Add null check for charger:
```python
if session.charger:
    session.charger.status = ChargerStatus.PAUSED
    session.charger.reason = ChargerReason.PAUSED_HIGH_LOAD
    session.charger.current = 0
    session.charger.stop_charging()
```

---

## 2. session.py

### Issue 2.1: `get_charger` (lines 65-75)
**Current code:**
```python
if session:
    logger.debug(
        "Vehicle %s is connected to charger %s", vehicle_id, session.charger.id
    )
    charger = self.get_charger_status_by_id(chargers, session.charger.id)
```

**Fix:** Add null check for `session.charger`:
```python
if session and session.charger:
    logger.debug(
        "Vehicle %s is connected to charger %s", vehicle_id, session.charger.id
    )
    charger = self.get_charger_status_by_id(chargers, session.charger.id)
```

### Issue 2.2: `get_session_by_vehicle` (lines 84-92)
**Current code:**
```python
if join:
    for session in self.current_sessions:
        if session.vehicle is None:
            logger.info(
                "Joining vehicle %s to existing session with charger %s",
                vehicle_id,
                session.charger.id,
            )
            return session
```

**Fix:** Add null check for charger:
```python
if join:
    for session in self.current_sessions:
        if session.vehicle is None and session.charger:
            logger.info(
                "Joining vehicle %s to existing session with charger %s",
                vehicle_id,
                session.charger.id,
            )
            return session
```

### Issue 2.3: `get_session_by_charger` (lines 103-109)
**Similar fixes needed for session.vehicle null check.**

---

## 3. messages.py

### Issue 3.1: Topic subscription (lines 134-146)
**Current code:**
```python
charger_status = SessionManager.get_charger_status_by_id(
    self.chargers, charger_config.id
)
if msg.topic == charger_config.status_topic:
    s = charger_status.map_status(msg.payload.decode())
    charger_status.status = s
```

**Fix:** Add null check for charger_status:
```python
charger_status = SessionManager.get_charger_status_by_id(
    self.chargers, charger_config.id
)
if charger_status and msg.topic == charger_config.status_topic:
    s = charger_status.map_status(msg.payload.decode())
    charger_status.status = s
```

### Issue 3.2: Vehicle status handling (lines 148-161)
**Current code:**
```python
vehicle_status = SessionManager.get_vehicle_status_by_id(
    vehicle.id, self.vehicles
)
if msg.topic == vehicle.connected_topic:
    value = _decode_bool(msg)
    if vehicle_status.connected != value:
```

**Fix:** Add null check for vehicle_status:
```python
vehicle_status = SessionManager.get_vehicle_status_by_id(
    vehicle.id, self.vehicles
)
if vehicle_status and msg.topic == vehicle.connected_topic:
    value = _decode_bool(msg)
    if vehicle_status.connected != value:
```

### Issue 3.3: Optional topic comparison (lines 184-188)
**Current code:**
```python
if msg.topic == self.config.power_consumption_topic:
    self._handle_float_message(msg, self._on_power_consumption_changed)

if msg.topic == self.config.power_production_topic:
```

**Fix:** Add null checks for topics:
```python
if self.config.power_consumption_topic and msg.topic == self.config.power_consumption_topic:
    self._handle_float_message(msg, self._on_power_consumption_changed)

if self.config.power_production_topic and msg.topic == self.config.power_production_topic:
```

---

## 4. planner.py

### Issue 4.1: `get_vehicle_config_by_id` return value (lines 135-150)
**Current code:**
```python
vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
# ...
target_soc=vehicle_config.target_soc,
```

**Fix:** Handle None return value:
```python
vehicle_config = self.config.get_vehicle_config_by_id(vehicle.id)
if not vehicle_config:
    logger.warning(f"No vehicle config found for {vehicle.id}")
    return None  # or return a default plan

planned_energy_kwh = self._get_planned_energy(vehicle, vehicle_config)
# ...
target_soc=vehicle_config.target_soc,
```

---

## 5. chargers.py

### Issue 5.1: `get_status` return type (lines 171-174)
**Current code:**
```python
def get_status(self) -> OperatingMode:
    details = self._client.get_charger_details(charger_id=self.settings.charger_id)
    op_mode = details.operating_mode
    return OperatingMode(op_mode)
```

**Fix:** Handle potential None from API call:
```python
def get_status(self) -> Optional[OperatingMode]:
    try:
        details = self._client.get_charger_details(charger_id=self.settings.charger_id)
        if details:
            op_mode = details.operating_mode
            return OperatingMode(op_mode)
    except Exception:
        logger.exception("Failed to get charger status")
    return None
```

### Issue 5.2: `map_status` return type (lines 176-188)
**Current code:**
```python
@staticmethod
def map_status(status: str):
```

**Fix:** Add return type:
```python
@staticmethod
def map_status(status: str) -> Optional[ChargerStatus]:
```

---

## Summary of Required Changes

| File | Issue | Fix |
|------|-------|-----|
| smartcharger.py:160 | session.vehicle/charger can be None | Add null checks before access |
| smartcharger.py:172-174 | get_vehicle_config_by_id returns None | Add null check |
| smartcharger.py:212-217 | session can be None | Add null check |
| smartcharger.py:228-231 | session.charger can be None | Add null check |
| session.py:71 | session.charger can be None | Add null check |
| session.py:86-90 | session.charger can be None | Add null check |
| messages.py:135-140 | charger_status can be None | Add null check |
| messages.py:149-161 | vehicle_status can be None | Add null check |
| messages.py:184-188 | Optional topic comparison | Add null check |
| planner.py:135-150 | vehicle_config can be None | Add null check |
| chargers.py:171-174 | API can return None | Add null check + return type |
