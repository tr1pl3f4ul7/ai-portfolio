# Mobile and web projects

Selected client work. Each entry lists the client and the date the work was delivered.

## Gruntify — GIS platform for field workers (Gruntify Pty Ltd, December 2021)

Built during Ljuben's contract as an Android Developer at Gruntify, April 2020 to January 2022.

Gruntify is an advanced GIS platform for managing field workers. The Android application is the
primary interface for two different groups: inspection teams who create requests, attach media and
define forms; and field workers who fill those forms in and report job status and real-time
location.

The platform supports white labelling for enterprise customers alongside a generic SaaS version.

Android development in Kotlin and Java, including augmented reality features, SQLite, RxJava and
Firebase. Available on Google Play as `com.gruntify.app`.

## Ozone Warehouse — warehouse process digitisation (Ozone Entertainment JSC, October 2019)

Built in-house while Ljuben was a Software Engineer at Ozone.bg — software for the company's own
warehouse staff, not for an external client.

The most operationally demanding project on this list. An Android application for warehouse
employees covering five modules: collection, sorting, zoning, revision and acceptance.

Its purpose was to digitise five core warehouse processes that had, until the first release, been
carried out with pen and paper.

Notable engineering constraints:

- It runs on the **Zebra TC8000**, an industrial-grade barcode scanner, not a phone.
- Some modules communicate with the backend per-list; others hold a constant connection, because
  the warehouse cannot operate correctly otherwise.
- The application runs in **kiosk mode** and **self-updates** from an in-house backend.

If this software stops working, physical work in the warehouse stops. That constraint drove every
significant design decision.

## Ozone Transport — driver logistics (Ozone Entertainment JSC, July 2019)

Also built in-house at Ozone.bg, for the company's own drivers.

Android application for company drivers. Lists of daily tasks with live reporting to the backend
for every successful or unsuccessful delivery, push notifications when the schedule changes
mid-route, and parcel barcode scanning using the phone camera.

## Montblanc Hub — smart writing hardware (Montblanc, April 2019)

Delivered through **Musala Soft**, where this was the single project Ljuben worked on for his
entire time at the consultancy.

The next version of Montblanc Hub, the companion application for Montblanc's smart writing set.

Two things made it difficult:

- **Adding support for a graphic tablet that was still in the hardware workshop** — building
  against hardware that did not yet exist in final form.
- **Supporting two paper sizes.** The original hardware was A5; the new device introduced A4. That
  sounds trivial and was not.

The work also fixed numerous Bluetooth connection problems and smoothed live mode and background
syncing of notes from the hardware.

## Atlantic Money — banking outside the branch (Banque Atlantique, November 2018)

A **Software Group** client project, built during Ljuben's time there delivering software for
financial institutions.

A project for a financial institution in Cameroon. The mobile application lets the client's
representatives operate as bank officers outside the premises, providing financial services to
customers in remote locations.

The interesting constraint here is context: financial services delivered where branch
infrastructure does not reach.

## MyKi Watch — children's smartwatch companion (Allterco, October 2017)

Built **in-house at Allterco**, where Ljuben was a Junior Android Developer. Allterco is a product
company and MyKi is its own product, so this was product team work rather than client services —
his first professional Android project.

MyKi Junior is a smartwatch for children. The companion mobile application gives parents a way to
communicate with their child and track fitness activity and location, and allows games on the
watch to be restricted to appropriate times of day and days of the week.

Consumer IoT with a genuine safety dimension, and a product whose users are parents but whose
wearers are children.

## Mtel TV Box — set-top box launcher (Mtel, September 2017)

Client work delivered through **Allterco**, which ran a substantial client services business
alongside its own products at the time.

A launcher kiosk application for a custom TV box, providing the custom menu functionality
requested by the mobile operator and an interface simple enough for television users.

A different interaction model to a phone: remote control navigation, ten-foot user interface,
constrained hardware.

## Happy Call — ringback tones (Vivacom, December 2016)

Also client work through **Allterco**, and one of Ljuben's earliest professional projects — from
his first months as a junior Android developer.

A WebView Android application providing a ringback tone service for a telecommunications operator,
using Firebase notifications and a JavaScript interface for backend communication.

## Stylebox — e-commerce for the family business (July 2018)

Not client work and not paid. Ljuben built this **for his mother's business, in his own time and
for free**: an OpenCart web store customised to her requirements, plus a companion WebView Android
application.

It was a hobby project that turned into a real revenue channel — the store went on to generate
significant income for the family business.

A small illustration of something that recurs across his career: the value came from solving an
actual business problem, not from the sophistication of the stack. Available on Google Play as
`com.ljubenvassilev.styleboxbulgaria`.
