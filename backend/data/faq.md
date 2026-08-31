# Frequently asked questions

Direct answers to the questions people actually ask, including the uncomfortable ones. Where the
honest answer is a limitation, it is stated as one.

## What does Ljuben actually do?

He is a **mobile and software engineer with ten years of experience**, most of it in mobile
development — Android in Java and Kotlin from 2016, then Flutter and Dart.

Around that core he has built two further specialisations: real-time 3D for VR and AR
(2017–2020), and application security (from 2021, including a Master's degree and three years as
an Application Security Engineer).

He is currently a Software Engineer at AI Talent, and is actively working to deepen his AI
expertise.

## Does Ljuben have AI experience?

Yes, though it is recent and practical rather than research-based. Being precise about what it is
and is not:

**What he has:**

- He works as a Software Engineer at **AI Talent** (from April 2026).
- He uses **Claude Code and GitHub Copilot daily in production work**, across multiple underlying
  models — as a working method, not an experiment.
- He holds the **Career Essentials in Generative AI** certification from Microsoft and LinkedIn.
- He designed and built **this site**, which runs AI inference in four distinct places: a language
  model in the visitor's browser, a classification model at the Cloudflare edge, a retrieval
  pipeline with a local embedding model on a server he provisioned and hardened himself, and a
  hosted model API for generation. The architectural reasoning is published as a decision log.

**What he does not have:** he is not an ML researcher. He has not trained or fine-tuned foundation
models, published papers, or worked on model architecture. His work is applied — building,
deploying and operating systems that use AI.

**What he brings to it** is ten years of shipping production software under real constraints, and
the judgement that comes with that. Knowing how to build an application that survives contact with
users, hardware limits and regulated environments transfers directly to building AI applications
that do the same. His security background adds a useful second lens — particularly around
untrusted input reaching a model, which is exactly the problem this site's contact form has to
solve.

## What is the most technically challenging thing he has built?

**Ozone Warehouse**, an Android application that digitised five core warehouse processes —
collection, sorting, zoning, revision and acceptance — which had previously been done with pen and
paper.

What made it hard was not the feature list but the operating constraints:

- It runs on **Zebra TC8000 industrial barcode scanners**, not phones.
- Some modules communicate with the backend per-list; others hold a **constant connection**,
  because the warehouse cannot operate correctly otherwise.
- It runs in **kiosk mode** and **self-updates** from an in-house backend, because staff cannot be
  asked to manage app installs mid-shift.
- **If the software stops, physical work in the warehouse stops.** That single fact drove every
  significant design decision.

Honourable mention to **Montblanc Hub**, which required building against a graphic tablet that was
still in the hardware workshop, and migrating the application from A5 to A4 paper support.

## He does not have a computer science degree. Is that a problem?

His first degree is a Master's in Finance. He entered software through the **IT Talents Training
Camp** bootcamp, then a junior Android role at Allterco, then ten years of production work.

He later completed a **Master of Information Technology in Cyber Security and Network Security** at
Charles Sturt University while working full time, graduating with a 6.25 average, an Academic
Achievement Award and an Executive Dean's Award.

So the honest position: no undergraduate CS degree, a decade of shipped production software, and a
postgraduate technical degree earned the hard way. The finance background has also been directly
useful on banking projects.

## Why were the early roles so short?

Because that is how the Bulgarian software market worked for a junior engineer at the time, and
because most of those roles were consultancy or contract positions where moving between
engagements is normal.

**Software Group** and **Musala Soft** were both consultancies — at Musala Soft he spent his entire
tenure on a single client project, Montblanc Hub. **Ozone.bg** was in-house product work.
**SolvedOut** was a short contract.

The pattern reverses once he settles: nearly two years at Gruntify, then **four years at
PropertyMe**, where he held two roles concurrently for three of them.

## Why does he show two jobs at PropertyMe at the same time?

Because he genuinely held both. From April 2023 to April 2026 he was simultaneously a **Software
Engineer** building Flutter applications for tenants and owners, and an **Application Security
Engineer** running penetration tests, code reviews and security automation.

It is not a title change listed twice. He did both jobs concurrently for three years.

## Why does freelance work overlap his full-time jobs?

His **vreestory** VR/AR freelance work ran from January 2018 to April 2020, alongside full-time
roles at Software Group, Musala Soft and Ozone.bg. That is intentional, not a data error — the
Unity3D work happened outside employed hours.

## Is his VR and AR experience current?

No, and that should be said plainly. The VR and AR work is concentrated between 2017 and 2020,
using Unity3D with Google Cardboard and Samsung GearVR. The headsets have moved on considerably
since.

The work itself covered educational games for government programmes (**Hood VR**, presented in
more than 20 schools), safety training (**Wincanton Fire Safety**), promotional experiences
(**OMV VR**), and film promotion — **Hellboy VR**, built at SolvedOut for Lions Gate.

Hellboy VR was the hardest of them. The brief was cinematic visual quality on a **phone-driven
headset**, where the entire render budget is a mobile GPU inside a plastic shell with no active
cooling and a hard frame-time ceiling before the viewer feels motion sickness. Getting film-grade
quality out of that is a genuine engineering constraint, not an art problem.

What remains current from all of it is the transferable part: working within hard performance
budgets, 3D and spatial reasoning, and shipping to unusual hardware.

## What else is he interested in?

Beyond his professional work, he follows several areas he has not yet had a working context to
develop properly:

- **Blockchain and distributed systems** — the consensus and trust mechanisms rather than the
  speculative side.
- **Tor and privacy-preserving networking** — onion routing, anonymity systems, and the
  engineering trade-offs they involve.
- **Applied cryptography**, as it appears in both of the above.

These are genuine interests rather than claimed expertise. He has not shipped production work in
any of them, and says so — the honest framing is broad technical curiosity with no professional
outlet yet, which is part of why he builds things like this site in his own time.

## What is this website, and how was it built?

It is a portfolio that deliberately runs AI inference in four different places, because the
architectural reasoning is the point:

| Layer | Where it runs | What it does |
|---|---|---|
| Browser | The visitor's own device | An on-device language model summarises his experience — no network call, no API cost |
| Edge | Cloudflare Workers AI | Screens contact form submissions for spam before they reach the backend |
| Server | An Oracle Cloud ARM VM he provisioned himself | This chatbot — retrieval over a local vector store |
| Cloud API | Z.AI's GLM API | Contact triage and answer generation |

The server is not a managed platform. He provisioned the VM, configured nginx, systemd, TLS and the
firewall, and set up CI/CD to four separate deploy targets. The decision log records what was
chosen, what was rejected, and why — including the mistakes.

## What kind of work is he looking for?

**Roles where he can develop his AI expertise further.** He is not fixed on a particular job title,
company size or industry — the priority is working somewhere AI is genuinely part of the
engineering, so that the applied experience he has been building on his own time becomes his day
job.

His decade of mobile engineering, his security background and his XR work are all things he brings
to that, rather than things he is looking to leave behind. A role combining any of them with AI
would suit him well.

He is based in Brisbane, Queensland, Australia, and is an experienced remote worker: remotely on
freelance projects since 2017, and in his contract and full-time roles since 2020.

## How do I contact him?

Through the contact form on this site. It is triaged automatically — classified and summarised —
so genuine enquiries reach him quickly.

He is also on LinkedIn at linkedin.com/in/lvassilev.

## What does "frameworks don't matter, satisfied customers do" mean?

It is his LinkedIn headline and a real position, not a slogan.

He has shipped production software in Java, Kotlin, Dart, C#, JavaScript and Unity/C#, on Android
phones, Flutter, VR headsets, industrial barcode scanners and TV set-top boxes. Across that range,
the framework was rarely the thing that determined success. The constraints were — a warehouse that
stops if the scanner app fails, a bank that needs auditability, a headset with a frame budget.

He picks tools to fit problems, and judges the result by whether it worked for the people using it.
