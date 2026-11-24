# Implementation Plan: hacs-sendblue

근거: [SPEC.md](SPEC.md). 각 작업은 테스트를 먼저 쓰고(TDD), 작업 하나당 커밋 하나. 모든 작업의 공통 검증은 `uv run pytest && uv run ruff check . && uv run ruff format --check .`.

## 구성요소와 의존 관계

```text
phone.py ─┐
api.py ───┼─> config_flow.py + __init__.py ─> coordinator.py ─┬─> notify.py (+ recipient subentry)
          │                                                    ├─> binary_sensor.py
          │                                                    └─> webhook 등록 수명주기 ─> webhook.py 핸들러 ─> Assist
```

- `phone.py`, `api.py`는 HA에 의존하지 않는 순수 모듈이라 먼저, 서로 병렬로 만들 수 있다.
- 나머지는 순서대로 진행한다 (config entry → coordinator → entity → webhook).

## 위험과 대응

| 위험 | 대응 |
|---|---|
| `sb-signing-secret` 헤더가 실제로 오는지 미확인 | T11 E2E에서 확인. 안 오면 secret을 URL 경로로 옮기는 대안으로 SPEC 수정 후 진행 |
| 비공식 `shared-contacts` API 변경·중단 | binary_sensor만 영향받게 격리 (T4 테스트로 보장) |
| 공유 번호 변경 | coordinator가 매번 회선 조회, repair issue (T4) |
| HA 개발 버전(2026.12.dev) 실사용 환경과 테스트 기준(2026.11) 차이 | `pytest-homeassistant-custom-component` 최신으로 테스트, E2E는 실제 인스턴스에서 |
| 무료 플랜 제약 오류(4007–4009, 미인증) | api 예외 매핑 + 번역된 오류 메시지 (T2, T5) |

## Tasks

### Phase A — 기반

- [x] **T0. 저장소 골격**
  - Acceptance: `git init`(main), `pyproject.toml`(uv, dev 의존성: `pytest-homeassistant-custom-component`, `pytest-cov`, `ruff`), `manifest.json`, `hacs.json`, `LICENSE`(MIT), `const.py`, 빈 `__init__.py`, `tests/conftest.py`, `.gitignore`. CI(hassfest, HACS validate, pytest) 워크플로.
  - Verify: `uv sync && uv run pytest`(테스트 0개 정상 종료), `uv run ruff check .`
  - Files: `pyproject.toml`, `custom_components/sendblue/{manifest.json,const.py,__init__.py}`, `hacs.json`, `LICENSE`, `.github/workflows/*.yml`

- [x] **T1. 수신자 주소 정규화** (T2와 병렬 가능)
  - Acceptance: `normalize_address(raw, default_region)` — `010-1234-5678`→`+821012345678`, `+82 010…`→`+8210…`, `+1 (555) 123-4567`→`+15551234567`, 이메일은 소문자화, 그 외 `ValueError`. 외부 라이브러리 없이 구현(국내 접두 `0` 규칙은 한국 등 국가번호 표로 한정).
  - Verify: `uv run pytest tests/test_phone.py`
  - Files: `custom_components/sendblue/phone.py`, `tests/test_phone.py`

- [x] **T2. Sendblue API 클라이언트**
  - Acceptance: `SendblueClient` — `get_lines`, `send_message`, `list_webhooks`, `add_webhook`, `delete_webhook`, `get_shared_contacts`. 예외: `SendblueAuthError`(401/403), `SendblueContactNotVerified`(`ContactHasNotBeenVerified`), `SendblueRateLimited`(429, 4001, 5509), `SendblueFreePlanLimit`(4007–4009), `SendblueError`. secret은 예외 메시지·repr에 포함 안 됨.
  - Verify: `uv run pytest tests/test_api.py` (`aioclient_mock`으로 헤더·본문·오류 매핑)
  - Files: `custom_components/sendblue/api.py`, `tests/test_api.py`

- [x] **T3. Config flow + entry 수명주기**
  - Acceptance: user step(키 2개 + `webhook_base_url`, `get_lines` 검증), `unique_id=api_key_id` 중복 중단, reauth, reconfigure(URL), options(`conversation_agent_id`). `async_setup_entry`가 클라이언트를 `runtime_data`에 넣고, `async_unload_entry` 정상 동작. `webhook_id`/`webhook_secret` 자동 생성.
  - Verify: `uv run pytest tests/test_config_flow.py tests/test_init.py` (config_flow 100% 커버리지)
  - Files: `config_flow.py`, `__init__.py`, `strings.json`, `tests/test_config_flow.py`, `tests/test_init.py`

**Checkpoint A**: 로컬 테스트로 계정 entry 생성·삭제가 된다. 사용자 리뷰.

### Phase B — 알림

- [x] **T4. Coordinator**
  - Acceptance: 30분 주기로 `get_lines` + `get_shared_contacts`. `shared-contacts` 실패는 인증 상태만 `None`. 회선 번호가 `entry.data`의 마지막 값과 다르면 repair issue 생성 후 값 갱신. `async_request_refresh`로 즉시 갱신 가능.
  - Verify: `uv run pytest tests/test_coordinator.py`
  - Files: `coordinator.py`, `__init__.py`, `strings.json`, `tests/test_coordinator.py`

- [x] **T5. 수신자 subentry + notify**
  - Acceptance: subentry flow(`name`, `address`→T1 정규화, `assist_enabled`), 같은 entry 내 주소 중복 거부, 설명에 현재 공유 번호 표시. 수신자별 device + `NotifyEntity`(title 합치기). Entity action `sendblue.send_message`(`message`, `title`, `media_url`, `send_style` select). API 예외 → 번역 키가 있는 `HomeAssistantError`, 발송 실패 시 coordinator 갱신 요청.
  - Verify: `uv run pytest tests/test_config_flow.py tests/test_notify.py`
  - Files: `config_flow.py`, `notify.py`, `services.yaml`, `strings.json`, `tests/test_notify.py`

- [x] **T6. 인증 상태 binary_sensor**
  - Acceptance: 수신자 device마다 `binary_sensor`(device_class 없음, 이름 "인증됨"), coordinator 데이터와 매핑, 인증 정보 없으면 unavailable.
  - Verify: `uv run pytest tests/test_binary_sensor.py`
  - Files: `binary_sensor.py`, `__init__.py`, `strings.json`, `tests/test_binary_sensor.py`

**Checkpoint B**: 실제 HA에 수동 복사로 설치해 notify 발송 확인 가능 (webhook 없이). 사용자 리뷰.

### Phase C — 수신·Assist

- [x] **T7. Webhook 등록 수명주기**
  - Acceptance: setup 시 HA webhook 등록 + Sendblue에 URL 없으면 `add_webhook`(이미 있으면 생략). 실패 시 repair issue만 띄우고 setup은 성공. unload 시 HA webhook 해제. `async_remove_entry`에서 Sendblue `delete_webhook`. reconfigure로 URL이 바뀌면 이전 URL 삭제 후 새 URL 등록.
  - Verify: `uv run pytest tests/test_init.py`
  - Files: `__init__.py`, `webhook.py`(등록 함수), `strings.json`, `tests/test_init.py`

- [x] **T8. Webhook 핸들러**
  - Acceptance: secret `hmac.compare_digest` 불일치 401 / JSON 오류 400 / outbound·group 무시 / `message_handle` 중복 무시(최근 256개) / `sendblue_message_received` 이벤트(SPEC 필드) / 항상 빠르게 200.
  - Verify: `uv run pytest tests/test_webhook.py` (`hass_client_no_auth`)
  - Files: `webhook.py`, `tests/test_webhook.py`

- [ ] **T9. Assist 응답**
  - Acceptance: `assist_enabled` 수신자 + 비어 있지 않은 `content`일 때만 background task로 `async_converse`(고정 `conversation_id`), 응답 speech를 같은 번호로 발송, 빈 응답 미발송, 예외 시 고정 오류 문구. 비허용·미등록 발신자는 이벤트만.
  - Verify: `uv run pytest tests/test_webhook.py`
  - Files: `webhook.py`, `tests/test_webhook.py`

**Checkpoint C**: 전체 테스트 + 커버리지(전체 95%, config_flow 100%). 사용자 리뷰.

### Phase D — 마무리

- [ ] **T10. 번역·문서**
  - Acceptance: `translations/en.json`, `translations/ko.json`(strings.json과 키 일치), README(설치, Sendblue 무료 가입·번호 인증 절차·E.164 주의, 공유 번호 변경 시 재인증, Assist 노출 entity, 보안 주의).
  - Verify: hassfest 통과 (CI 또는 로컬 `docker`/`linux-test` 머신), `uv run pytest`
  - Files: `translations/en.json`, `translations/ko.json`, `README.md`

- [ ] **T11. HA OS 실기 E2E** — *Ask first: GitHub 공개 저장소 생성·push*
  - Acceptance: SPEC Success Criteria 1–10 체크리스트 전부 통과. 특히 9번(`sb-signing-secret` 헤더) 확인.
  - Verify: 수동 체크리스트 결과를 PR/이슈에 기록
  - Files: 없음 (발견 사항은 SPEC 실측 결과에 추가)
