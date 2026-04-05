# CTEK Charger API Documentation

This document describes the CTEK charger API based on the implementation in this codebase. The API is used to communicate with CTEK Smart Chargers via the CTEK IoT cloud service.

## Base URL

```
https://iot.ctek.com
```

## Authentication

The CTEK API uses OAuth 2.0 authentication with two methods:

### 1. Password Grant

```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>&grant_type=password&password=<PASSWORD>&username=<USERNAME>
```

**Response:**
```json
{
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 3600,
    "token_type": "Bearer"
}
```

### 2. Refresh Token Grant

```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>&grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>
```

### Headers

All authenticated requests require:
```http
Authorization: Bearer <ACCESS_TOKEN>
Accept: */*
Content-Type: application/json
User-Agent: CTEK/2.4.0 (se.ctek.ctekapp; build:3; iOS 15.5.0) Alamofire/2.4.0
Accept-Language: sv-SE;q=1.0, en-SE;q=0.9
```

---

## Implemented API Calls

### Device Information

#### Get Device Status

Get the current status of the charger device.

```http
GET /devices/{device_id}/status
```

**Response:** Returns `DeviceInfo` object with:
- `device_name` - Name of the device
- `connectors` - List of connectors with status
- `hardware_id` - Hardware identifier
- `device_type` - Type of device
- `connected` - Online status
- `model` - Device model
- `schedule` - Schedule configuration
- `configuration` - Device configuration
- `firmwareVersion` - Current firmware version
- `loadBalancingOnboarded` - Load balancing status
- `thirdPartyOcppInfo` - Third-party OCPP configuration

---

### Charging Sessions

#### Get Current Session

Get information about the ongoing charging session.

```http
GET /devices/{device_id}/sessions/current
```

**Response:** Returns `ChargingSessionSummary` object with:
- `device_id` - Device identifier
- `ongoing_transaction` - Whether a transaction is active
- `transaction_id` - Current transaction ID
- `watt_hours_consumed` - Energy consumed in current session (Wh)
- `momentary_voltage` - Current voltage
- `momentary_power` - Current power (W)
- `momentary_current` - Current current (A)
- `device_online` - Device online status
- `type` - Session type
- `start_time` - Session start timestamp
- `last_updated_time` - Last update timestamp

---

#### Get Charging History

Get historical charging sessions.

```http
GET /api/v1/devices/{device_id}/sessions/charging?pageSize=20&page=0&fromDate=<ISO_DATE>&toDate=<ISO_DATE>
```

**Query Parameters:**
- `pageSize` - Number of results per page (default: 20)
- `page` - Page number (default: 0)
- `fromDate` - Start date filter (ISO format)
- `toDate` - End date filter (ISO format)

**Response:** Returns paginated list of charging sessions including:
- `meter_stop` - Meter reading at session end (Wh)
- `start_time` - Session start
- `stop_time` - Session end
- `energy_delivered` - Energy delivered

---

### Charging Schedules

#### Get All Schedules

```http
GET /schedule/transactions?deviceId={device_id}
```

**Response:** Returns `ChargingSchedules` object with:
- `list` - Array of `ChargingSchedule` objects
- `total_pages` - Total number of pages
- `total_elements` - Total number of schedules
- `current_page` - Current page number
- `page_size` - Page size

---

#### Get Single Schedule

```http
GET /api/v3/schedule/transaction?id={schedule_id}
```

---

#### Create Schedule (v2)

```http
POST /schedule/transaction
Content-Type: application/json

{
    "device_id": "...",
    "period_list": [
        {
            "limit": 16,
            "start": {
                "day": "MONDAY",
                "hour": "22",
                "minute": "00"
            },
            "stop": {
                "day": "TUESDAY",
                "hour": "06",
                "minute": "00"
            }
        }
    ],
    "unit": "A",
    "time_zone": "+02:00"
}
```

---

#### Create Schedule (v3)

```http
POST /api/v3/schedule/transaction?pushToDevice=true
Content-Type: application/json

{
    "id": null,
    "device_id": "...",
    "unit": "A",
    "period_list": [...],
    "connector_id": 1,
    "active": true,
    "user_enabled": true,
    "time_zone": "+02:00",
    "pending_deletion": false
}
```

---

#### Update Schedule

```http
POST /api/v3/schedule/transaction?pushToDevice=true
Content-Type: application/json

{
    "id": 123,
    "device_id": "...",
    ...
}
```

---

#### Delete Schedule

```http
DELETE /schedule/transaction?id={schedule_id}
```

---

#### Delete All Schedules

```http
DELETE /schedule/transactions?deviceId={device_id}
```

---

### Device Control

#### Enable/Disable Charging

Resume or pause charging.

```http
POST /api/v3/device/control
Content-Type: application/json

{
    "device_id": "...",
    "instruction": "RESUME_CHARGING",  // or "PAUSE_CHARGING"
    "connector_id": 1
}
```

---

### Device Configuration

#### Set Maximum Current

Set the maximum charging current limit.

```http
POST /api/v3/device/configurations?deviceId={device_id}&pushToDevice=true
Content-Type: application/json

{
    "CurrentMaxAssignment": "16"
}
```

**Valid current limits:** 6, 8, 10, 12, 14, 16 Amps

---

## Data Structures

### ChargingSchedule

```python
@dataclass
class ChargingSchedule:
    id: Optional[int]
    device_id: str
    unit: str                    # "A" for Amps
    period_list: List[Period]   # Charging periods
    connector_id: int
    active: bool                # Is schedule active
    user_enabled: bool          # User enabled
    time_zone: str              # e.g., "+02:00"
    pending_deletion: bool = False
    author_id: Optional[int] = None
```

### Period

```python
@dataclass
class Period:
    start: TimePeriod
    stop: TimePeriod
    limit: float                 # Current limit in Amps

@dataclass
class TimePeriod:
    day: str           # MONDAY, TUESDAY, etc.
    hour: int
    minute: int
```

### Days Enum

```python
class DAYS(int, Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
```

### Connector Status

```python
@dataclass
class Connector:
    id: int
    deviceId: str
    currentStatus: str
    statusReason: str
    statusString: str
    status: int
    startDate: Optional[datetime]
    updateDate: Optional[datetime]
```

---

## Likely Unimplemented API Calls

Based on common EV charger APIs and the patterns observed, these endpoints likely exist but are not implemented in this codebase:

### Device Management

| Endpoint | Description |
|---------|-------------|
| `GET /devices` | List all devices for user |
| `GET /devices/{device_id}` | Get device details |
| `PUT /devices/{device_id}` | Update device settings |
| `DELETE /devices/{device_id}` | Remove device |

### Energy/Metering

| Endpoint | Description |
|---------|-------------|
| `GET /devices/{device_id}/meter` | Get current meter reading |
| `GET /api/v1/devices/{device_id}/energy` | Get energy statistics |
| `GET /devices/{device_id}/measurements` | Get real-time measurements |

### User Management

| Endpoint | Description |
|---------|-------------|
| `GET /user/profile` | Get user profile |
| `PUT /user/profile` | Update user profile |
| `GET /user/devices` | Get user's devices |

### Smart Features

| Endpoint | Description |
|---------|-------------|
| `GET /api/v1/smart-charging` | Get smart charging settings |
| `PUT /api/v1/smart-charging` | Update smart charging |
| `GET /api/v1/grid-status` | Get grid status |
| `POST /api/v1/charge-now` | Start immediate charging |

### Firmware

| Endpoint | Description |
|---------|-------------|
| `GET /devices/{device_id}/firmware` | Get firmware info |
| `POST /devices/{device_id}/firmware/update` | Trigger firmware update |

### Diagnostics

| Endpoint | Description |
|---------|-------------|
| `GET /devices/{device_id}/diagnostics` | Get diagnostic data |
| `GET /devices/{device_id}/logs` | Get device logs |

---

## Error Handling

### Error Response Format

```json
{
    "error": "error_code",
    "message": "Error description"
}
```

### Common Error Codes

| Error Code | Description |
|------------|-------------|
| `invalid_token` | Access token expired or invalid |
| `invalid_grant` | Invalid credentials |
| `device_not_found` | Device doesn't exist |
| `schedule_not_found` | Schedule doesn't exist |
| `invalid_configuration` | Invalid device configuration |

---

## Configuration Required

To use the CTEK API, you need:

```yaml
ctek:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  username: "your_email@example.com"
  password: "your_password"
  device_id: "your_device_id"
```

The API uses token caching to avoid repeated logins. Tokens are stored in `~/.ctek/credentials_cache.yaml`.

---

## Notes

- The API appears to be versioned (v1, v2, v3 endpoints)
- Time zones are hardcoded to `+02:00` (CEST) in schedules
- All timestamps are in ISO format
- The API requires user-agent spoofing to work (appears to target mobile app)
