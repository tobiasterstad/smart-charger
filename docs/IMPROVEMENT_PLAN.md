# Smart Charger Improvement Plan

## Overview

This document outlines improvements to make the smart-charger production-ready.

---

## Priority 1: Critical (Must Fix)

### 1.1 Move Zaptec Credentials to secret.py

**Current state:** Credentials hardcoded in `smartcharger.py:67-75`

**Location:** `src/smart_charger/smartcharger.py`

```python
# Current (bad)
settings = ZaptecSettings(
    username=secret.username,
    password=secret.password,
    installation_id=secret.installation_id,
    charger_id=secret.charger_id,
    ...
)
```

**Action:**
- Add Zaptec credentials to `src/smart_charger/secret.py`
- Import from secret in smartcharger.py

---

### 1.2 Add Circuit Breaker & Rate Limiting

**Current state:** No retry logic; failures crash the app

**Affected files:** 
- `src/smart_charger/zaptec.py`
- `src/smart_charger/tibber/tibber_util.py`
- `src/smart_charger/lib/ctek/ctek_util.py`

---

#### Circuit Breaker Pattern

The circuit breaker prevents cascading failures when external APIs are unavailable.

**States:**
```
CLOSED (Normal) → OPEN (Blocked after failures) → HALF-OPEN (Testing)
```

**Configuration:**
```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3      # Failures before opening circuit
    timeout_seconds: int = 60       # Seconds before trying again
    half_open_calls: int = 1       # Test calls allowed in half-open state
```

**Implementation:**
```python
class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = "CLOSED"
        self.failures = 0
        self.last_failure_time = 0

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.config.timeout_seconds:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpen("Circuit is open")
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
```

**Apply to these methods:**
| Service | Method | Rationale |
|---------|--------|-----------|
| Zaptec | `start_charging`, `stop_charging`, `set_current`, `get_status` | External API |
| Tibber | `get_prices`, `get_current_price` | External API |
| CTEK | `get_status`, `set_enable_charging`, `set_max_current` | External API |

---

#### Rate Limiting

Controls how often external APIs can be called to avoid overwhelming them.

**Recommended Limits:**

| API | Max Calls | Time Window | Notes |
|-----|-----------|-------------|-------|
| Zaptec API | 60 | per minute | Per installation |
| Tibber API | 100 | per hour | Free tier |
| CTEK Cloud | 60 | per minute | Per device |

**Implementation:**
```python
class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: list[float] = []

    def acquire(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.window_seconds]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.window_seconds - (now - self.calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.acquire()  # Retry after sleeping
        
        self.calls.append(now)
```

**Apply to:**
- Tibber price updates (cache prices, don't fetch every check)
- Zaptec status updates (cache status, fetch max every 30s)
- CTEK status (fetch max every 60s)

**Best Practice:**
- Cache responses locally
- Only refresh when cache expires
- Background refresh, not on-demand

---

#### Retry with Exponential Backoff

For transient failures, retry with increasing delays.

```python
def retry_with_backoff(func, max_retries=3, base_delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
```

**Action:**
- Add circuit breaker class to `src/smart_charger/utils/`
- Add rate limiter class
- Wrap all external API calls
- Add configuration to `config.py`
- Log circuit state changes

---

### 1.3 Add Connection Timeout Handling

**Current state:** Blocking calls to charger APIs

**Action:**
- Add timeouts to all HTTP requests (requests library already imported)
- Use `asyncio` for non-blocking charger commands

---

## Priority 2: Important (Should Fix)

### 2.1 Dynamic Solar Surplus Charging Current

**Current state:** Fixed 6A when solar excess detected

**Location:** `src/smart_charger/smartcharger.py:235`

**Action:**
- Calculate charging current based on available excess
- Formula: `current = min(excess_watts / 230, 16)` (max 16A)
- Add smoothing to prevent rapid current changes

---

### 2.2 Planner Integration with Solar Forecast

**Current state:** Planner doesn't use solar predictions effectively

**Location:** `src/smart_charger/planner.py`

**Action:**
- Add solar forecast provider (from Tibber or weather API)
- Modify `PriceAwarePlanner` to consider solar windows
- Schedule charging during predicted solar peaks

---

### 2.3 Add Logging Configuration

**Current state:** Basic `logging.basicConfig` only

**Action:**
- Add file-based logging with rotation
- Configure log levels via config file
- Add request IDs for tracing

---

## Priority 3: Nice to Have

### 3.1 CTEK Nanogrid Air Local API Support

**Current state:** Uses cloud API (`iot.ctek.com`)

**Background:** Nanogrid Air has simpler local REST API:
- HTTP Basic Auth (username: `ctek`)
- Endpoints: `/status/`, `/config/`
- No OAuth needed

**Action:**
- Create new `NanogridAirCharger` class
- Add to `ChargerType` enum
- Update config

---

### 3.2 Add Unit Tests for CTEK Library

**Current state:** 0% test coverage

**Location:** `src/smart_charger/lib/ctek/`

**Action:**
- Mock HTTP requests
- Test all CTEK API methods
- Add to CI pipeline

---

### 3.3 Systemd Service File

**Current state:** No service configuration

**Action:**
- Create `smart-charger.service`
- Configure auto-start on boot
- Add restart policy

---

### 3.4 Docker Support

**Current state:** No containerization

**Action:**
- Create Dockerfile
- Create docker-compose.yml
- Add .dockerignore

---

## Priority 4: Future Enhancements

### 4.1 Multiple Vehicle Support
- Handle simultaneous charging for multiple vehicles
- Prioritize vehicles by SOC or user preference

### 4.2 Grid Load Balancing
- Monitor high-load topics
- Automatically reduce charging during peaks

### 4.3 Web Dashboard
- Current status view
- Manual override controls
- Historical charts

### 4.4 Voice Assistant Integration
- Alexa/Google Home commands
- "Start charging now"

---

## Implementation Order

```
Sprint 1 (This week):
├── 1.1 Move Zaptec credentials to secret.py
├── 1.2 Add retry logic for charger APIs
└── 1.3 Add connection timeouts

Sprint 2 (Next week):
├── 2.1 Dynamic solar charging current
├── 2.2 Add logging configuration
└── 2.3 Planner solar integration (basic)

Sprint 3 (This month):
├── 3.1 CTEK local API support
├── 3.2 Unit tests for CTEK
└── 3.3 Systemd service

Sprint 4+:
├── 4.1 Docker support
├── 4.2 Web dashboard
└── 4.3 Advanced features
```

---

## Notes

- All changes should maintain backward compatibility
- Keep integration tests separate from unit tests
- Document any new configuration options
- Update this plan as priorities shift
