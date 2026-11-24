# Home Assistant용 Sendblue

[English](README.md)

[Sendblue](https://sendblue.com)를 통해 Home Assistant에서 가족에게 iMessage를 보내고, 가족이 답장으로 Assist에 말을 걸어 집을 제어할 수 있게 합니다. Mac이나 여분 iPhone이 필요 없습니다. 메시지는 Sendblue의 Apple 기기가 보냅니다.

- 사람마다 `notify` entity가 생겨서 자동화에서 `notify.send_message`를 그대로 쓸 수 있습니다.
- `sendblue.send_message` 액션으로 이미지(`media_url`)나 iMessage 효과(`send_style`)를 붙일 수 있습니다.
- 받은 메시지마다 `sendblue_message_received` 이벤트가 발생합니다.
- 허용한 사람의 메시지에는 Assist가 답장합니다.
- 사람마다 "인증됨" 센서가 있어서 Sendblue가 그 사람에게 보낼 수 있는지 알 수 있습니다.

## 준비물

- Home Assistant 2026.10 이상
- 외부에서 접속되는 HTTPS 주소 (Nabu Casa 원격 URL이나 자체 도메인). 받은 메시지가 이 주소로 들어옵니다. 보내기만 할 거라면 없어도 됩니다.
- Sendblue 계정. 무료 플랜 기준으로 만들었습니다.

## 설치

1. HACS → **사용자 지정 저장소**에 `https://github.com/saya6k/hacs-sendblue`를 **통합구성요소**로 추가하고 **Sendblue**를 설치합니다.
2. Home Assistant를 재시작합니다.

## Sendblue 설정

1. 무료 계정을 만듭니다: `npx -y @sendblue/cli@latest setup` 또는 [대시보드](https://dashboard.sendblue.com)에서 가입.
2. API 키와 시크릿을 확인합니다: `npx -y @sendblue/cli@latest show-keys`
3. Home Assistant **설정 → 기기 및 서비스 → 통합구성요소 추가 → Sendblue**에서 키, 시크릿, 공개 URL을 입력합니다.

webhook은 Sendblue에 자동으로 등록되고, 통합구성요소를 삭제하면 함께 지워집니다. 계정의 다른 webhook은 건드리지 않습니다.

## 가족 추가

Sendblue 통합구성요소에서 **수신자 추가**를 누르고 이름과 전화번호(또는 Apple ID 이메일)를 입력합니다. 문자로 집을 제어해도 되는 사람에게만 **Assist 허용**을 켜세요.

그다음 그 사람이 등록한 번호의 휴대폰으로 **Sendblue 번호에 문자를 한 번** 보내야 합니다. 번호는 추가 화면과 모든 메시지의 발신자로 표시됩니다. 보내기 전까지는 Sendblue가 발송을 거부하고 **인증됨** 센서가 꺼져 있습니다.

번호는 휴대폰이 실제로 보내는 형식과 정확히 같아야 합니다. `010-1234-5678` 같은 국내 번호는 Home Assistant 국가 설정에 따라 `+821012345678`로 바뀝니다. `+82010…`으로 등록된 번호는 인증되지 않습니다.

### 공유 번호가 바뀌었을 때

무료 플랜의 Sendblue 번호는 여러 사용자가 함께 쓰며 바뀔 수 있습니다. 바뀌면 Home Assistant에 새 번호를 알려 주는 수리 알림이 뜨고, 모든 수신자가 새 번호로 문자를 한 번씩 보내야 합니다.

## 사용법

```yaml
action: notify.send_message
target:
  entity_id: notify.mom
data:
  title: 현관
  message: 문이 열렸어요.
```

```yaml
action: sendblue.send_message
target:
  entity_id: notify.mom
data:
  message: 택배 도착
  media_url: https://example.com/snapshot.jpg
  send_style: celebration
```

iMessage에는 제목 칸이 없어서 `title`은 메시지 첫 줄로 들어갑니다. `media_url`은 외부에서 열리는 주소여야 하고 파일 확장자로 끝나야 합니다.

### 받은 메시지

```yaml
triggers:
  - trigger: event
    event_type: sendblue_message_received
    event_data:
      recipient_name: 엄마
```

이벤트 데이터: `entry_id`, `from_number`, `content`, `media_url`(30일 후 만료), `service`, `message_handle`, `recipient_subentry_id`, `recipient_name`(등록되지 않은 사람이면 `null`). 단체 대화와 이 통합구성요소가 보낸 메시지는 이벤트가 발생하지 않습니다.

### Assist

**Assist 허용**이 켜진 사람의 메시지는 Assist로 전달되고, 답이 문자로 돌아갑니다. 기본으로 선호하는 Assist 파이프라인의 대화 에이전트와 언어를 쓰며, 통합구성요소의 **구성**에서 다른 에이전트를 고를 수 있습니다. Assist는 [Assist에 노출한](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/) entity만 제어할 수 있습니다. 대화 맥락은 사람별로 5분 동안 유지됩니다.

기본 대화 에이전트는 표현에 엄격합니다. 예를 들어 "지금 몇 시야"는 알아듣지만 "지금 몇시야?"는 못 알아듣습니다. LLM 기반 에이전트가 더 유연합니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| "아직 인증되지 않은 수신자입니다" | 등록한 번호 그대로의 휴대폰에서 Sendblue 번호로 문자를 보내야 합니다. **인증됨** 센서를 확인하세요. |
| 문자를 보냈는데 인증됨이 계속 꺼짐 | 한국 번호는 `+8210…`이어야 합니다(`+82010…` 아님). 수신자를 `010-…` 형식으로 다시 추가하세요. |
| 답장이 Home Assistant에 안 들어옴 | "수신 메시지를 받을 수 없습니다" 수리 알림을 확인하고, 공개 URL이 외부에서 열리는지 본 뒤 통합구성요소를 다시 불러오세요. |
| Assist가 "이해하지 못했습니다"라고 답함 | 대화 에이전트의 답입니다. 같은 문장을 Assist 창에서 시험해 보거나 **구성**에서 다른 에이전트를 고르세요. |
| 어느 순간부터 메시지가 안 감 | 무료 공유 번호가 바뀌었을 수 있습니다. 수리 알림의 새 번호로 모두가 문자를 한 번 보내야 합니다. |

디버그 로그:

```yaml
logger:
  logs:
    custom_components.sendblue: debug
```

## 보안

- 들어오는 요청은 설정할 때 Home Assistant가 만든 secret이 있어야 하며, 없으면 거부합니다.
- 수신자가 아니거나 Assist가 허용되지 않은 사람의 메시지는 이벤트만 발생하고 Assist에는 전달되지 않습니다.
- 메시지는 Sendblue 서버를 거칩니다. 제3자에게 맡기기 어려운 내용은 보내지 마세요.

## 무료 플랜 제한

- 공유 번호 하나에 인증된 연락처 10명까지
- 연락처가 먼저 문자를 보내야 함
- 연락처가 답장하기 전에는 메시지 수와 길이가 제한됨(약 6개, 300자). 오류는 자동화 추적에 표시됩니다.

Sendblue는 해당 소유자의 상표이며, 이 프로젝트는 Sendblue와 관계가 없습니다.

## 라이선스

MIT
