# Design

Scope: the private chat surface (`public/chat.html`, served at `/chat`). The older anonymizer tester (`public/index.html`) keeps its own look until it is redesigned.

## World

Follows Wispr Flow (https://wisprflow.ai/), pinned by the user: a warm paper ground, a literary serif for display lines with an italic turn, a friendly sans for everything you read or operate, thin ink outlines instead of shadows, and one soft lavender for the primary action.

## Color (restrained: neutrals + one action color)

| Role | Value | Use |
|------|-------|-----|
| Paper | `#FFFFEB` | Page ground |
| Paper deep | `#F6F5DC` | Composer field, AI-view surfaces |
| Line | `#E4E4D0` | Hairlines, quiet borders |
| Ink | `#1A1A1A` | Text, outlines, user bubbles |
| Ink soft | `#55554A` | Secondary text (≥4.5:1 on paper) |
| Lavender | `#F0D7FF` | Primary button, restored-value highlights |
| Forest | `#1F4A3D` | Announcement bar, placeholder tokens |
| Forest tint | `#E2EADB` | Placeholder token ground |
| Coral | `#C2410C` | Warnings text only (darkened from Wispr's `#FF6C4C` for contrast) |

## Type

- Display: EB Garamond 400, italic for the emphasized half of a headline. Only headlines and the empty-state prompt suggestions.
- UI and reading: Figtree 400/500/600.
- Placeholders (`[PERSON_01]`) are data and render in the system monospace stack.

## Components

- Buttons: 8px radius, 1px ink border, lavender fill for primary, paper fill for secondary. No shadows.
- Segmented pill: rounded-full track in Line color, active segment Paper with ink text (mirrors Wispr's Dictation/Notetaker switch). Used for navigation and the per-exchange "You / The AI" view switch.
- Containers: 16px radius, 1px Line border. No nested cards, no colored side borders.
- Restored values: lavender highlight with 4px radius. Placeholders: forest tint ground, forest text, monospace.

## Motion

One authored moment: the waveform pill (Wispr's signature) breathes while a request is in flight. View switching crossfades with a short blur. All motion stops under `prefers-reduced-motion`.
