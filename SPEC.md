# Spec: Sendblue for Home Assistant (HACS custom integration)

## Assumptions

1. 대상 환경은 **Home Assistant OS**이며, Mac/여분 iPhone 없이 Sendblue 클라우드 API만 사용한다.
2. 요금제는 **무료 공유 회선(free shared line)** 기준으로 설계한다. 유료 전용 회선에서도 동작은 하되 별도 기능은 넣지 않는다.
3. 메시지 수신자는 **가족(최대 10명)** 이며, 각자 Sendblue 번호로 한 번 문자를 보내 인증을 마친 상태를 전제로 한다. 사용자 본인도 수신자로 등록할 수 있다.
   - `from_number`는 Sendblue가 할당한 회선 번호이며 개인 번호로 지정할 수 없다 ("must be a Sendblue number on your account").
4. HA 외부 노출은 사용자가 입력한 **base URL**(자체 도메인 또는 Nabu Casa remote URL)로 한다. Nabu Casa cloudhook API는 쓰지 않는다.
5. Sendblue 공식 SDK는 쓰지 않고 HA가 제공하는 `aiohttp` 세션으로 REST를 직접 호출한다 (의존성 0개).
6. 기준 버전: Home Assistant 2026.11, Python 3.14.

## Objective

HA 자동화에서 가족에게 iMessage(불가 시 SMS)로 알림을 보내고, 허용된 가족이 문자로 Assist에 말을 걸어 집을 제어할 수 있게 한다.

### User stories

- 자동화 작성자로서, `notify.send_message`로 특정 가족에게 iMessage를 보낼 수 있다.
- 자동화 작성자로서, 이미지(`media_url`)나 효과(`send_style`)를 붙여 보낼 수 있다.
- 가족 구성원으로서, Sendblue 번호에 "거실 불 꺼줘"라고 보내면 Assist가 실행하고 결과를 답장한다 (해당 가족에게 Assist가 허용된 경우).
- 자동화 작성자로서, 수신 문자를 이벤트로 받아 직접 자동화를 만들 수 있다.
- 관리자로서, 등록되지 않았거나 Assist가 허용되지 않은 번호의 문자는 집을 제어하지 못함을 신뢰할 수 있다.

### Scope

| In (MVP) | Out (명시적 제외) |
|---|---|
| UI config flow (계정) + 수신자 subentry | 그룹 메시지 발송/수신 처리 |
| 수신자별 `notify` entity | reactions, typing indicator, read receipt, App Card, carousel |
| `sendblue.send_message` entity action (`media_url`, `send_style`) | 파일 업로드 (`/api/upload-file`) |
| 수신 webhook 자동 등록/해제 | `status_callback`/`outbound` 상태 추적 |
| 수신 이벤트 `sendblue_message_received` | 전화/FaceTime |
| 수신자별 Assist 응답 | Nabu Casa cloudhook |
| en / ko 번역 | HACS default 저장소 등록 |

## Sendblue API (구현 근거)

출처: <https://docs.sendblue.com/llms.txt>, `/getting-started/sending-messages`, `/getting-started/webhooks`, `/security`

- Base URL `https://api.sendblue.com`, 헤더 `sb-api-key-id`, `sb-api-secret-key`.
- 발송: `POST /api/send-message` — `number`(E.164 또는 이메일), `from_number`(**무료 공유 회선은 필수**), `content` | `media_url`, `send_style`(13종).
  - 상태: `REGISTERED|PENDING|DECLINED|QUEUED|ACCEPTED|SENT|DELIVERED|ERROR`.
  - 무료 플랜 제약: 첫 답장 전 300자/6개 제한(오류 코드 4007–4009), 미인증 연락처 발송 불가.
- 회선 조회: `GET /api/lines`.
- Webhook: `GET|POST|DELETE /api/account/webhooks`, `type: "receive"`, 항목은 `{url, secret}`. POST는 기존 목록에 **추가**, PUT은 **전체 교체**(사용 금지).
  - 수신 요청 헤더 `sb-signing-secret` 값이 설정한 secret과 일치해야 한다 (HMAC 아님, 단순 비교).
  - 5xx 응답 시 최대 3회 재시도, 응답 대기 45초, 410 응답 시 Sendblue가 webhook 삭제.
- 수신 payload 주요 필드: `from_number`, `to_number`, `content`, `media_url`, `service`, `is_outbound`, `message_handle`, `group_id`, `date_sent`.

### 실측 결과 (2026-11-25, 무료 플랜 `free_api` 계정)

- `GET /api/lines` → `{"numbers": ["+1…"]}`: 무료 플랜에서도 공유 번호 반환.
- `GET /api/account/webhooks` → `rawBodySigningAvailable: false` 포함. 무료 플랜에선 raw body 서명 불가 → `sb-signing-secret` 단순 비교 유지. GET 응답에 secret이 평문으로 포함됨.
- `POST /api/account/webhooks` (`{webhooks:[{url, secret}], type:"receive"}`) 무료 플랜에서 동작.
- **공유 회선 연락처는 비공개 API로 관리됨** (`@sendblue/cli` 0.10.0 소스 기준, 공개 문서에 없음):
  - `POST /accounts/verify-contact-on-shared-account` `{recipient}` → 연락처 등록 (CLI `add-contact`).
  - `GET /accounts/shared-contacts` → `{sharedNumber, contacts:[{id, number, verified, createdAt}]}`.
  - `/api/v2/contacts`는 빈 목록을 반환하며 공유 회선 연락처와 무관.
- 미인증 연락처로 발송 시 HTTP 400, `error_reason: "ContactHasNotBeenVerified"`.
- **공유 번호는 바뀔 수 있음**: 가입 직후 수 분 내에 할당 번호가 변경됐고, 연락처도 새 ID로 재생성(미인증 상태)됨. CLI `credentials.json`의 `assignedNumber`는 갱신되지 않음.
- `GET /api/evaluate-service`는 +82 번호에 대해 `service: iMessage` 반환.
- **+82 번호 인증 성공 — 원인은 번호 형식**: 가입 시 연락처가 `+82010…`(국내 접두 `0` 포함, 잘못된 E.164)으로 등록되어 실제 발신 번호 `+8210…`과 매칭되지 않았다. 올바른 형식으로 문자를 보내자 `+8210…` 연락처가 새로 생기며 즉시 `verified: true`. 잘못된 연락처는 미인증 상태로 남는다.
  → 수신자 주소는 **E.164로 엄격히 정규화**해야 한다 (한국 `010-xxxx-xxxx` → `+8210xxxxxxxx`, `+82010…` 입력도 교정 또는 거부).
- 인증 직후 Sendblue가 연락처에게 "You've been verified on …" iMessage를 자동 발송한다.
- 수신 webhook 실측 payload (HA로 도착 확인): `accountEmail, content, is_outbound=false, status="RECEIVED", message_handle(UUID 대문자), date_sent, date_updated, from_number, number, to_number, plan, media_url="", message_type="message", group_id="", participants=[], service="iMessage", sendblue_number, opted_out, multipart{id,index,count}` 등. 수신은 문자 발송 후 약 2초 내 도착.
- 발송 응답: HTTP **202**, `status: "QUEUED"`, `message_handle` 반환 (동기 응답에서 `service`는 null). 줄바꿈·이모지 그대로 전달, 수 초 내 `DELIVERED`.
- 수신 iPhone에 푸시 알림 정상 표시 (공유 번호가 발신자라 본인 번호를 수신자로 써도 알림이 뜬다).
- 발송된 메시지에 일반 답장 → 같은 webhook으로 수신 (`reply_to`/`thread_originator`는 null).
- `DELETE /api/account/webhooks` `{webhooks:[url], type:"receive"}` → 해당 URL만 삭제됨.
- **HA OS 실기 E2E (2026-11-25, HA 2026.12.0.dev, SSH로 수동 설치)**: config flow·subentry(REST) 정상, webhook 자동 등록(secret 64자), `binary_sensor` 인증 on, `notify.send_message`(title 첫 줄)·`sendblue.send_message`(이미지+celebration) 도착. 실제 Sendblue 요청이 `sb-signing-secret` 검증을 통과해 이벤트 발생 → **헤더 방식 확인됨**. Assist 왕복 약 2–5초 ("지금 몇 시야" → "오전 7시 1분"). 기본 agent는 띄어쓰기에 민감("몇시야?"는 미인식). Entry 삭제 시 Sendblue receive webhook 1→0개, entity 제거 확인.
- HA `conversation.async_converse`: ULID가 아닌 `conversation_id`를 넘기면 그 값을 그대로 세션 ID로 사용 (`helpers/chat_session.py`, 2026.11.3). 세션은 5분 동안 사용이 없으면 만료.

## Design

### Config entry (계정 1개)

| 필드 | 저장 위치 | 비고 |
|---|---|---|
| `api_key_id`, `api_secret_key` | `data` | 검증: `GET /api/lines` 200 + 번호 1개 이상 |
| `webhook_base_url` | `data` | 기본값: `get_url(hass, allow_internal=False, prefer_external=True)`, 실패 시 빈 칸. `https://`만 허용 |
| `webhook_id`, `webhook_secret` | `data` | 생성 시 `secrets.token_hex(32)` 등으로 자동 생성, UI 노출 안 함 |
| `conversation_agent_id` | `options` | 기본 `conversation.home_assistant` |

- `from_number`는 **저장하지 않는다** (공유 번호가 바뀜). Coordinator가 갱신한 현재 회선을 쓴다.
- `unique_id` = `api_key_id` (같은 계정 중복 등록 방지).
- reauth flow (401/403 시), reconfigure flow (`webhook_base_url` 변경).

### Coordinator (회선·인증 상태)

- `DataUpdateCoordinator`, 30분 주기 + 발송 실패 시 즉시 갱신 요청.
  - `GET /api/lines` → 현재 `from_number` (첫 번째 번호).
  - `GET /accounts/shared-contacts` (비공식) → 수신자별 `verified`. 실패해도 coordinator는 실패시키지 않고 인증 상태만 unknown 처리.
- 회선 번호가 이전 값과 다르면 repair issue "공유 번호가 {new}로 바뀌었습니다. 가족이 새 번호로 문자를 한 번씩 보내야 합니다"를 띄운다 (마지막으로 본 번호는 `entry.data`에 기록해 재시작 후에도 비교).
- 수신자별 `binary_sensor` "인증됨"(`verified`)을 제공한다. 인증 정보를 못 얻으면 unavailable.
- 연락처 등록은 API로 하지 않는다: 가족이 공유 번호로 문자를 보내면 Sendblue가 연락처를 자동 생성·인증한다 (실측). Subentry 추가 화면 설명에 "이 번호로 문자를 보내세요: {from_number}"를 표시.
- `line_assigned` webhook은 payload 형식이 문서화되지 않아 쓰지 않는다.

### Subentry: 수신자 (`recipient`)

| 필드 | 비고 |
|---|---|
| `name` | entity/device 이름 |
| `address` | E.164 전화번호 또는 Apple ID 이메일. 저장 전 정규화: 공백/하이픈 제거, 국내형(`010…`)은 HA 국가 설정으로 `+8210…` 변환, 국가번호 뒤 `0`(`+82010…`)은 제거. 정규화 불가 시 오류 |
| `assist_enabled` | bool, 기본 `false` |

- 수신자 1명 = device 1개 + `notify` entity 1개 (`notify.sendblue_<name>`).
- 같은 entry 안에서 `address` 중복 불가.

### 발송

- `NotifyEntity.async_send_message(message, title)` → `content = f"{title}\n{message}"` (title 없으면 message만).
- Entity action `sendblue.send_message` (target: 이 integration의 notify entity)
  - `message` (필수), `title`, `media_url`(https, 확장자로 끝남), `send_style`(select 13종).
- API 오류는 `HomeAssistantError`(번역 키 포함)로 올려 자동화가 실패를 알 수 있게 한다. 무료 플랜 제약 오류(4007–4009, 미인증)는 원인을 알 수 있는 메시지로 매핑.

### 수신 webhook

1. Entry 설정 시 `webhook.async_register(..., local_only=False, allowed_methods=["POST"])`.
2. URL = `{webhook_base_url}/api/webhook/{webhook_id}`.
3. Sendblue 등록: `GET`으로 이미 있는지 확인 → 없으면 `POST {webhooks:[{url, secret}], type:"receive"}`.
   - 실패해도 entry 설정은 실패시키지 않는다(발송은 동작해야 하므로). 대신 repair issue를 띄우고 로그를 남긴다.
4. Entry 제거(`async_remove_entry`) 시 해당 URL만 `DELETE`. reconfigure로 URL이 바뀌면 이전 URL 삭제 후 새 URL 추가.
5. 핸들러 처리 순서:
   1. `sb-signing-secret`을 `hmac.compare_digest`로 비교. 불일치 → 401, 이후 아무것도 안 함.
   2. JSON 파싱 실패 → 400.
   3. `is_outbound`가 true이거나 `group_id`가 있으면 → 200 후 무시.
   4. `message_handle`이 최근 처리 목록(메모리, 최대 256개)에 있으면 → 200 후 무시 (재시도 중복 방지).
   5. 이벤트 `sendblue_message_received` 발생:
      `{entry_id, from_number, content, media_url, service, message_handle, recipient_subentry_id | None, recipient_name | None}`.
   6. 발신자가 `assist_enabled` 수신자와 일치하고 `content`가 비어있지 않으면 → background task로 Assist 처리.
   7. 즉시 200 반환 (Assist 완료를 기다리지 않음, 45초 timeout 회피).

### Assist

- `conversation.async_converse(hass, text=content, conversation_id=f"sendblue_{entry_id}_{from_number}", context=Context(), language=hass.config.language, agent_id=options.conversation_agent_id)`.
- ULID가 아닌 고정 ID는 HA가 그대로 세션 ID로 쓰므로 별도 보관이 필요 없다. 5분 동안 대화가 없으면 맥락이 초기화된다.
- `response.speech["plain"]["speech"]`를 같은 발신자에게 `send-message`로 답장. 빈 응답이면 보내지 않는다.
- Assist 예외 발생 시 짧은 고정 오류 문구로 답장하고 로그에 남긴다.
- 제어 범위는 Assist에 **노출(exposed)된 entity**로 제한된다(HA 기본 동작). README에 명시.

## Tech Stack

- Python 3.14, Home Assistant ≥ 2026.10.0 (테스트 기준: `pytest-homeassistant-custom-component` 최신판이 고정한 2026.10.4)
- 런타임 의존성 없음 (`aiohttp`는 HA 내장, `async_get_clientsession`)
- 개발: `uv`, `pytest-homeassistant-custom-component`, `ruff`
- CI: GitHub Actions — hassfest, HACS action, pytest

## Commands

```bash
uv sync                                         # 개발 환경
uv run pytest                                   # 전체 테스트
uv run pytest --cov=custom_components.sendblue --cov-report=term-missing
uv run ruff check . && uv run ruff format --check .
uv run ruff check --fix . && uv run ruff format .
```

수동 E2E (HA OS):

```text
HACS → Custom repositories → https://github.com/saya6k/hacs-sendblue (Integration) → 설치 → HA 재시작
설정 → 기기 및 서비스 → 통합구성요소 추가 → Sendblue
```

## Project Structure

```text
custom_components/sendblue/
  __init__.py        → setup/unload/remove, webhook 등록·해제, runtime_data
  api.py             → Sendblue REST 클라이언트 (send, lines, webhooks), 예외 타입
  binary_sensor.py   → 수신자별 인증 상태
  config_flow.py     → config/reauth/reconfigure flow, options flow, recipient subentry flow
  const.py           → DOMAIN, 키 이름, SEND_STYLES, 이벤트 이름
  coordinator.py     → 현재 회선·연락처 인증 상태 갱신, 회선 변경 repair issue
  phone.py           → 수신자 주소 정규화 (E.164 / 이메일)
  notify.py          → 수신자별 NotifyEntity + sendblue.send_message entity action
  webhook.py         → 수신 핸들러, 중복 제거, 이벤트 발생, Assist 처리
  manifest.json      → domain, version, iot_class=cloud_push, dependencies [webhook, conversation]
  services.yaml
  strings.json
  translations/{en,ko}.json
tests/
  conftest.py
  test_api.py
  test_config_flow.py
  test_notify.py
  test_webhook.py
  test_init.py
  test_coordinator.py
  test_phone.py
.github/workflows/   → validate.yml (hassfest + HACS), tests.yml
hacs.json
pyproject.toml
README.md            → 설치, Sendblue 무료 플랜 인증 절차, 보안 주의사항
SPEC.md
```

## Code Style

- HA core 스타일: 전부 async, 타입 힌트 필수, `entry.runtime_data`에 typed dataclass, 사용자 노출 오류는 `translation_key`로.
- 상수는 `const.py`, 로그는 `_LOGGER = logging.getLogger(__name__)`. 메시지 본문과 secret은 로그에 남기지 않는다.
- ruff 기본 규칙 + HA 권장 규칙셋.

```python
class SendblueClient:
    """Thin async wrapper around the Sendblue REST API."""

    def __init__(self, session: ClientSession, key_id: str, secret: str) -> None:
        self._session = session
        self._headers = {"sb-api-key-id": key_id, "sb-api-secret-key": secret}

    async def send_message(
        self,
        number: str,
        from_number: str,
        content: str | None = None,
        media_url: str | None = None,
        send_style: str | None = None,
    ) -> dict[str, Any]:
        body = {"number": number, "from_number": from_number}
        body |= {
            k: v
            for k, v in (("content", content), ("media_url", media_url), ("send_style", send_style))
            if v
        }
        return await self._request("POST", "/api/send-message", json=body)
```

## Testing Strategy

- 프레임워크: `pytest-homeassistant-custom-component` (`hass`, `aioclient_mock`, `hass_client_no_auth`).
- Sendblue는 전부 `aioclient_mock`으로 대체, 실제 네트워크 호출 없음.
- 레벨별 책임:
  - `test_api.py`: 헤더, 본문 구성, 오류 코드 → 예외 매핑.
  - `test_config_flow.py`: 성공, 인증 실패, 회선 조회 실패 시 수동 입력, 중복 entry 중단, reauth, reconfigure, subentry 추가/수정/중복 주소 거부.
  - `test_notify.py`: entity 생성, title 합치기, entity action의 `media_url`/`send_style`, API 오류 → `HomeAssistantError`.
  - `test_webhook.py`: secret 불일치 401, 잘못된 JSON 400, outbound/group 무시, 중복 handle 무시, 이벤트 데이터, 미등록·Assist 비허용 발신자는 이벤트만 발생, 허용 발신자는 `async_converse` 호출 후 답장, 대화 ID 이어짐, Assist 예외 시 오류 답장.
  - `test_init.py`: setup 시 webhook 등록(이미 있으면 POST 생략), 등록 실패 시 repair issue와 notify 정상 동작, unload, remove 시 DELETE.
  - `test_coordinator.py`: 회선 갱신, 번호 변경 시 repair issue(재시작 후에도 비교), `shared-contacts` 실패 시 발송 계속·binary_sensor unavailable, 인증 상태 매핑.
  - `test_phone.py`: `010-1234-5678`·`+82010…`·`+82 10 …`·이메일·잘못된 입력 정규화.
- 커버리지 목표: `custom_components/sendblue` 95% 이상, `config_flow.py` 100%.
- 수동 E2E는 HA OS 실기기에서 Success Criteria 체크리스트로 1회 수행.

## Boundaries

- **Always**
  - 커밋 전 `uv run pytest`와 `ruff` 통과.
  - webhook 요청은 secret 검증을 먼저 통과해야 이후 단계로 진행 (fail closed).
  - 문서화되지 않은 Sendblue 동작을 가정하면 SPEC의 Open Questions에 기록.
- **Ask first**
  - 런타임 의존성 추가 (예: `sendblue` PyPI SDK).
  - Scope 표의 Out 항목 구현 (그룹, typing indicator 등).
  - Sendblue `PUT /api/account/webhooks` 등 계정 전체 설정에 영향 주는 호출.
  - 공개 저장소 생성/push, 릴리스 태그, HACS default 등록.
- **Never**
  - API secret, webhook secret, 전화번호, 메시지 본문을 로그·이벤트 외 경로(진단, 예외 메시지)에 노출.
  - 이 integration이 만들지 않은 Sendblue webhook 수정/삭제.
  - 미등록 또는 `assist_enabled=false` 발신자의 문자로 Assist 실행.
  - `.env` 등 자격 증명 파일 커밋.

## Success Criteria

1. `uv run pytest` 전부 통과, 커버리지 목표 달성, hassfest·HACS validation CI 통과.
2. HA OS에서 HACS custom repository로 설치 후 UI만으로 계정·수신자 2명 설정 가능.
3. `notify.send_message`로 인증된 가족 iPhone에 iMessage 도착 (title 포함 확인).
4. `sendblue.send_message`로 `media_url` 이미지와 `send_style: celebration` 효과가 도착.
5. Sendblue `GET /api/account/webhooks`에 integration URL이 정확히 1개 등록되고, entry 삭제 후 사라진다.
6. Assist 허용 가족이 "거실 불 켜줘"를 보내면 해당 entity가 켜지고 답장이 10초 내 도착 (기본 agent 기준).
7. Assist 비허용 가족 및 미등록 번호의 문자는 `sendblue_message_received` 이벤트만 발생하고 아무 동작/답장 없음.
8. 잘못된 `sb-signing-secret`으로 보낸 요청은 401이며 이벤트가 발생하지 않는다.
9. 실제 Sendblue 요청에 `sb-signing-secret` 헤더가 포함되어 검증을 통과한다.
10. 수신자별 "인증됨" binary_sensor가 Sendblue 상태와 일치한다.

## Open Questions

1. ~~라이선스~~ → 결정: **MIT**.
2. ~~+82 연락처 인증 불가~~ → 해결: 번호 형식 문제(`+82010…`). 올바른 E.164면 즉시 인증됨.
3. ~~공유 번호 변경 대응~~ → 결정: Design의 Coordinator 항목. 비공식 API는 읽기 전용(`shared-contacts`)만 쓰고, 실패해도 핵심 기능(발송·수신)에는 영향 없게 한다.
4. ~~`GET /api/lines` 무료 플랜 동작~~ → 해결: 동작함.
5. ~~`async_converse` 임의 `conversation_id`~~ → 해결: `sendblue_<entry_id>_<address>` 형태 고정 ID 사용 가능. 발신자별 ID 보관 불필요 (Design의 Assist 항목은 차단 이슈 해소 후 갱신).
6. **Assist 실행 사용자 context**: HA 사용자를 수신자에 연결(`user_id`)해 권한/로그 귀속을 할지. MVP는 연결하지 않음.
7. **공유 회선 수신 라우팅**: 인증된 연락처의 문자만 내 webhook으로 오는지는 인증 성공 후 확인.
