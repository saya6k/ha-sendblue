# Sendblue for Home Assistant

[한국어](README.ko.md)

Send iMessages from Home Assistant to your family through [Sendblue](https://sendblue.com), and let them text back to control the house with Assist. No Mac or spare iPhone needed: Sendblue's own Apple hardware sends the messages.

- One `notify` entity per person, so `notify.send_message` works in any automation.
- A `sendblue.send_message` action that adds an image (`media_url`) or an iMessage effect (`send_style`).
- A `sendblue_message_received` event for every incoming message.
- Optional Assist replies for the people you allow.
- A "Verified" sensor per person showing whether Sendblue will deliver to them.

## Requirements

- Home Assistant 2026.10 or newer.
- A public HTTPS address for Home Assistant, such as your Nabu Casa remote URL or your own domain. Sendblue posts incoming messages there. Sending works without it.
- A Sendblue account. The free plan works and is what this integration is designed around.

## Install

1. In HACS, open **Custom repositories**, add `https://github.com/saya6k/hacs-sendblue` as an **Integration**, then install **Sendblue**.
2. Restart Home Assistant.

## Set up Sendblue

1. Create a free account: `npx -y @sendblue/cli@latest setup`, or sign up in the [dashboard](https://dashboard.sendblue.com).
2. Get your API key and secret: `npx -y @sendblue/cli@latest show-keys`.
3. In Home Assistant go to **Settings → Devices & services → Add integration → Sendblue**, enter the key, the secret and your public URL.

The integration registers its webhook with Sendblue automatically and removes it again when you delete the integration. Other webhooks on your account are left alone.

## Add family members

Open the Sendblue integration and choose **Add recipient**. Enter a name and a phone number (or Apple ID email). Turn on **Allow Assist** only for people who should be able to control your home by text.

Each person must then **text the Sendblue number once** from that phone. The number is shown in the add screen and as the sender of every message. Until they do, Sendblue refuses to deliver to them and the person's **Verified** sensor stays off.

Numbers must match exactly what the phone sends. Local numbers such as `010-1234-5678` are converted to international form (`+821012345678`) using your Home Assistant country setting. A number registered as `+82010…` will never verify.

### When the shared number changes

On the free plan your Sendblue number is shared and can be reassigned. When that happens Home Assistant shows a repair notice with the new number, and every recipient has to text the new number once.

## Use it

```yaml
action: notify.send_message
target:
  entity_id: notify.mom
data:
  title: Front door
  message: The door was opened.
```

```yaml
action: sendblue.send_message
target:
  entity_id: notify.mom
data:
  message: Package delivered
  media_url: https://example.com/snapshot.jpg
  send_style: celebration
```

iMessage has no subject line, so `title` is sent as the first line of the message.

`media_url` must be publicly reachable and end in the file extension.

### Incoming messages

Every message fires `sendblue_message_received` with `from_number`, `content`, `media_url`, `service`, `message_handle`, and the matching `recipient_name` (or `null` for unknown senders):

```yaml
triggers:
  - trigger: event
    event_type: sendblue_message_received
    event_data:
      recipient_name: Mom
```

### Assist

Messages from recipients with **Allow Assist** turned on are passed to Assist, and the answer is texted back. By default the conversation agent and language of your preferred Assist pipeline are used; pick a different agent under the integration's **Configure** button. Assist can only control entities you have [exposed to Assist](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/). Each person keeps their conversation context for 5 minutes. The built-in agent is strict about wording; in Korean, for example, it understands "지금 몇 시야" but not "지금 몇시야?". An LLM-based agent is more forgiving.

## Reference

### Entities

Each recipient gets a device with:

| Entity | Description |
|---|---|
| `notify.<name>` | Sends to this person. |
| `binary_sensor.<name>_verified` | On when Sendblue will deliver to this person. Unavailable if Sendblue doesn't report it (the free-plan contact list is read from an undocumented endpoint). |

### Action `sendblue.send_message`

Target one or more Sendblue `notify` entities.

| Field | Required | Description |
|---|---|---|
| `message` | yes | Text to send. |
| `title` | no | Sent as the first line. |
| `media_url` | no | Public HTTPS URL ending in the file extension (`.jpg`, `.png`, `.mp4`, …). |
| `send_style` | no | One of `celebration`, `shooting_star`, `fireworks`, `lasers`, `love`, `confetti`, `balloons`, `spotlight`, `echo`, `invisible`, `gentle`, `loud`, `slam`. iMessage only. |

### Event `sendblue_message_received`

| Key | Description |
|---|---|
| `entry_id` | The Sendblue config entry. |
| `from_number` | Sender, in E.164 form. |
| `content` | Message text (empty for media-only messages). |
| `media_url` | Attachment URL, or empty. Sendblue expires it after 30 days. |
| `service` | `iMessage`, `SMS` or `RCS`. |
| `message_handle` | Sendblue's message ID. |
| `recipient_subentry_id`, `recipient_name` | The matching recipient, or `null`. |

Group messages and messages sent by the integration itself don't fire the event.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "This recipient is not verified yet" | The person must text the Sendblue number from the exact number you registered. Check the **Verified** sensor. |
| Verified sensor stays off after texting | The number stored in Sendblue must match what the phone sends. Korean numbers must be `+8210…`, not `+82010…`. Re-add the recipient with the local form (`010-…`). |
| Replies don't arrive in Home Assistant | Look for the "cannot deliver incoming messages" repair. Check that the public URL opens from outside your network, then reload the integration. |
| Assist answers "I didn't understand" | That is the conversation agent's answer. Try the same sentence in the Assist dialog, or pick another agent under **Configure**. |
| Messages stop after a while | Your free shared number may have changed. Follow the repair notice and ask everyone to text the new number. |

Enable debug logging with:

```yaml
logger:
  logs:
    custom_components.sendblue: debug
```

## Security

- Incoming requests must carry the secret Home Assistant generated during setup; anything else is rejected.
- Messages from people who are not recipients, or who don't have Assist allowed, only fire the event. They never reach Assist.
- Messages pass through Sendblue's servers. Don't send anything you wouldn't trust a third party with.

## Free plan limits

- Up to 10 verified contacts on a shared number.
- A contact must text you first.
- Before a contact replies, messages are limited (about 6 messages, 300 characters). The integration reports these errors in the automation trace.

## Development

```bash
uv sync
uv run pytest --cov=custom_components.sendblue
uv run ruff check . && uv run ruff format --check .
```

[SPEC.md](SPEC.md) records the design and what was verified against the live Sendblue API; [PLAN.md](PLAN.md) is the implementation plan.

The brand images in `custom_components/sendblue/brand/` are rendered from Sendblue's own logo. Sendblue is a trademark of its owner; this project is not affiliated with Sendblue.

## License

MIT
