# Accessibility

fahrma aims at [WCAG 2.2](https://www.w3.org/TR/WCAG22/) level AA: usable with a keyboard alone, with a screen reader, with large text and at 320 px width, in the light and the dark scheme.

## What is built in

- **Keyboard:** every action works without a mouse. The focus ring is 3 px wide and has a contrast of at least 3 : 1. A "Skip to content" link leads past the navigation. Tabs (history, administration) move with the arrow keys, Home and End.
- **Changing pages:** after a change of page the focus moves to the start of the content, as after a page load, and screen readers announce the new page's heading. The window title names the page ("New trip · fahrma").
- **State in words:** a running trip, a settled entry, a draft waiting for the connection or a failed login are said in text, not only shown by colour or an icon. Messages and errors are live regions.
- **Dialogs** (confirmations, receipt photos) are native modal dialogs: the focus stays inside and returns to the button that opened them.
- **Text size:** on iPhone and iPad the text follows the system text size, because an installed web app has no browser zoom; elsewhere the browser's zoom and font size work without sideways scrolling down to 320 px.
- **Touch targets** are at least 44 px high.
- **Motion:** animations and transitions only run when the system does not ask for reduced motion.
- **Colour:** the colour pairs of the theme meet the WCAG contrast minimum in both schemes.

The rules behind this are part of the [design language](design-language.md).

## How it is checked

Automatically, for every change (see [Development](development.md)):

- `npm test` checks the colour pairs of the theme against the contrast minimum in both schemes.
- The end-to-end tests run [axe](https://github.com/dequelabs/axe-core) with the WCAG 2.2 AA rules in Chromium and in WebKit on an iPhone screen, in both schemes, on:
  - every page of a group as it loads, the profile and the login page (`e2e/tests/design.spec.ts`);
  - every tab of the instance administration, the expense, reservation and import forms, a form showing an error, the confirmation dialog, the receipt photos, the pages without an account (registration, forgotten password, an invalid invitation link) and the English interface (`e2e/tests/accessibility.spec.ts`).
- The same tests check that no page scrolls sideways at 320 px and that after a change of page the focus is at the content and the page is announced.

Automated tests find only part of all problems. Checks by hand with screen readers (VoiceOver on iPhone and macOS, NVDA on Windows) are planned before 1.0.

## Known limits

- The interface is in German and English only.
- Push notifications come from the operating system; how they read out depends on it.

## Reporting a problem

If something does not work for you with a keyboard, a screen reader, a magnifier or another aid, please open an issue on GitHub and name the page, the device, the browser and the aid. Problems that block use are treated like bugs.
