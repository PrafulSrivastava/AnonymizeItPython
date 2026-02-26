Here are 20 test cases covering the full range of scenarios the pipeline needs to handle — from easy catches to deliberate edge cases designed to break it.

Group 1 — Clean WhatsApp format, structural PII (Step 01 should catch all)
[26/02/2026, 09:14] Sarah Müller: Hi everyone! Can someone help me understand the onboarding flow? My email is sarah.mueller@gmail.com and I've been stuck for 2 days.
[26/02/2026, 11:32] James O'Brien: Just joined the group! My number is +44 7911 123456 if anyone wants to chat directly. Also follow me @jamesobrien_dev on Instagram.
[26/02/2026, 14:05] Priya Sharma: Quick question — does the app support IBAN payments? Mine is DE89 3704 0044 0532 0130 00 and I want to test the checkout flow.

Group 2 — Age and date of birth variations (Step 01 edge cases)
[26/02/2026, 10:22] Anna Klein: I'm 34 and honestly the app UX is confusing for someone my age. My mum who is 67 years old also tried it and gave up immediately.
[26/02/2026, 08:45] Tom Fischer: Born in 1989 so I've seen a lot of apps come and go. This one has potential but the progress tracking feature is broken.
[26/02/2026, 16:18] Lena Bauer: I signed up on my birthday — 14.03.1991 — and the welcome email never arrived. Can someone check?

Group 3 — NER edge cases — short names, nicknames, ambiguous (Step 02 stress test)
[26/02/2026, 13:01] Susi: Hey! Is the community feature live yet? My colleague Mo asked me the same thing yesterday and I didn't know what to tell him.
[26/02/2026, 09:55] Ali: The push notifications stopped working for me after the last update. Ali from the Berlin team had the same issue btw.
[26/02/2026, 17:44] User: Can you tag Mei on this? She was the one who reported the bug last week and I think she has the screenshot.

Group 4 — Quasi-identifier combinations (Step 03 should flag)
[26/02/2026, 11:10] Maria Gonzalez: As a senior product manager based in Munich, aged 41, I find the dashboard completely unintuitive. This would never pass a basic usability test.
[26/02/2026, 15:33] David: I'm a freelance developer in Frankfurt, been coding for 15 years. The API docs are outdated — the endpoint at /api/v1/users returns a 404.

Group 5 — Obfuscated PII — designed to dodge regex (Step 01 hard cases)
[26/02/2026, 12:44] Jonas Weber: Reach me at jonas dot weber at protonmail dot com — I don't post my email publicly anymore after the last spam wave.
[26/02/2026, 10:08] Claire: My number is 0049 (0) 160 9876 5432 — old German format, not sure if your system recognises it. Happy to jump on a call.
[26/02/2026, 14:52] Fatima Al-Hassan: You can find me at linkedin.com/in/fatima-al-hassan-pm or just search my name — I'm the only one with that exact name on there.

Group 6 — Mixed language / code-switched (NER stress test, likely review queue)
[26/02/2026, 09:30] Björn Eriksson: Das Feature funktioniert nicht auf meinem iPhone. Björn here btw, Maide hat mir die Gruppe empfohlen. Danke schon mal!
[26/02/2026, 16:05] Yuki Tanaka: すみません、I'm having trouble with the login page. Yuki from the Tokyo cohort — can someone from support help?

Group 7 — Sensitive topic flags (Step 03 sensitive keyword detection)
[26/02/2026, 13:28] User: I need to be honest — I've been dealing with some health issues lately and the app's reminder feature has actually been really helpful for keeping me on track with medication.
[26/02/2026, 11:55] Rebecca Hofer: Not sure if this is the right place but I'm going through a divorce and the shared account feature is causing me real problems. Can someone from the team contact me directly?

Group 8 — Minimal PII, should pass cleanly (true negatives — pipeline must not over-redact)
[26/02/2026, 10:00] User: The dark mode on Android is broken. When I switch from light to dark the nav bar stays white. Happens every time on version 2.4.1.
[26/02/2026, 15:15] User: Love the new onboarding flow update! The three-step wizard is much clearer than before. One suggestion — add a progress bar so users know how far along they are.