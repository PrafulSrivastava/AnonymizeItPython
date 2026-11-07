# Design

Scope: the private chat surface (`public/chat.html`, served at `/chat`). The older anonymizer tester (`public/index.html`) keeps its own look until it is redesigned.

## World

Security envelope. The blue crosshatch printed inside security envelopes exists to hide what is inside; here it marks what the AI is allowed to see. Cool white stationery, deep ink-blue type, typewritten address-label placeholders, and a marigold highlighter for the details that come back to you.

## Color (restrained: neutrals + ink + one highlighter)

| Role | Value | Use |
|------|-------|-----|
| Paper | `#F5F7FB` | Page ground |
| Paper deep | `#EAEEF6` | Inputs, quiet fills |
| Line | `#D5DCEA` | Hairlines, quiet borders |
| Tint | `#E2E8F4` | Security-pattern ground |
| Ink | `#14224A` | Text, primary button, user bubbles, announcement bar |
| Ink soft | `#4A5677` | Secondary text (about 7:1 on Paper) |
| Marigold | `#FBD98A` | Restored-detail highlight |
| Marigold deep | `#E9A923` | Focus ring on dark ink surfaces |
| Alert | `#B42318` | Warning text |

Security pattern: two 1px diagonal hatch layers at ±45°, ink at 7% opacity, 6px pitch, over Tint.

## Type

- Schibsted Grotesk 400/500/700 for headlines and UI. Headlines are 700 with -0.03em tracking; the emphasized half is 500 italic.
- Courier Prime for placeholders (`[PERSON_01]`) only, because they are typed labels, not prose.

## Components

- Buttons: 8px radius. Primary is Ink fill with Paper text; secondary is Paper with a Line border.
- Segmented switch: 8px-radius track in Line, active segment Paper. Used for navigation and the per-exchange "You / The AI" view switch.
- "The AI" view: message surfaces take the security pattern; placeholders render as typewritten labels.
- Envelope window: a Paper rectangle with an Ink hairline set into a security-pattern strip; shows the example of what the AI sees.
- No shadows except the composer's focus lift; no nested cards; no colored side borders.

## Motion

One authored moment: the waveform pill breathes while a request is in flight. View switching crossfades with a short blur. Everything stops under `prefers-reduced-motion`.
