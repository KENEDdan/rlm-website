# Staff guide: managing the RLM website

This guide is for ministry staff. You do not need any technical knowledge. Each section says **who** can do
the task. If a menu item in this guide is missing for you, your role does not include it. That is on
purpose: everyone only sees what they need.

---

## 1. Everyone

### 1.1 Signing in
1. Open the staff sign-in page (the Founder will give you the address; it is **not** `/admin/`).
2. Enter your email and password.
3. **First time only:** you will see a QR code. Install an authenticator app on your phone (Google
   Authenticator, Microsoft Authenticator or Authy), tap "add account", scan the code, then type the 6-digit
   number the app shows. You will then see **10 backup codes**: write them on paper and keep them somewhere
   safe. Each works once if you lose your phone.
4. Every other time: after your password, type the current 6-digit number from the app.

Sign in **immediately** after the Founder creates your account: whoever signs in first sets up the
authenticator.

### 1.2 Rules for every staff member
* Use a long password (at least 12 characters) that you use **nowhere else**. A password manager helps.
* Never share your account, password, phone codes or backup codes, not even with the Founder.
* Lock your computer when you step away. Sign out on shared computers.
* The site signs you out after 2 hours without activity, and when you close the browser.
* After 5 wrong passwords your account is locked for one hour. Ask the Founder if you are locked out.
* Never download prayer requests or volunteer lists to a personal or shared computer. Never forward them by
  email or WhatsApp.
* Be suspicious of any email asking you to sign in "urgently" or send codes. The website will never ask for
  your authenticator code by email.
* Everything you open, change, export or delete is recorded in the audit log.

### 1.3 Lost phone or backup codes
Ask the Founder to use **Users → select you → "Reset two-factor"**. At your next sign-in you will scan a new
QR code. If you still have your phone, press **New backup codes** at the top right of the admin to get a fresh
set; the old ones stop working immediately.

### 1.4 Things that work the same everywhere
* **Published / not published:** only published items appear on the website. Untick to hide something
  without deleting it.
* **Slug:** the last part of the web address (e.g. `youth-conference`). Use lowercase words and dashes.
* **SEO title / description:** optional text for Google. Leave blank to use the normal title.
* **Body text:** plain text. Leave an empty line between paragraphs. A line starting with `## ` becomes a
  heading. Links and HTML are not accepted (this protects the site).
* **Images:** JPG, PNG or WebP, up to 8 MB. The site removes hidden location data from photos and makes
  small, fast versions automatically. Always fill in the **alt text** (a short description for blind
  visitors), e.g. "Young people worshipping at the Juba conference".
* **Searching submissions:** names and messages are encrypted, so the search box only finds an **exact email
  address** or an **ID number**. Use the filters on the right for everything else.

---

## 2. Secretary
*Contacts, prayer requests, volunteers, events, news, leadership.*

### 2.1 Handling new submissions
You get an email "New prayer request received". It contains **no** details on purpose. Click the link and
sign in to read it.

1. Open **Prayer requests**, **Contact messages** or **Volunteer applications**.
2. Click an item to read it. Add private notes in **Internal notes** (only staff see them).
3. When done, change **Status** to *Handled*, or tick several items in the list, choose **"Mark selected as
   handled"** and press **Go**.

Prayer requests marked *keep confidential* must not be shared with anyone outside the prayer team.

### 2.2 Exporting a list (only when really needed)
Tick the items → **"Export selected to CSV"** → **Go**. The export is recorded in the audit log. Delete the
file as soon as you have finished with it.

### 2.3 Old submissions are deleted automatically
By default prayer requests and contact messages are deleted after 365 days, volunteer applications after
730 days. The Founder can change this in **Site settings**.

### 2.4 Leaders
**Leaders** appear on the Leadership page only when **both** *Confirmed by leadership* **and** *Published* are
set. All officers except the Founder start as "To be confirmed".

### 2.5 Events and news
See sections 4 and 5. They are the same steps.

### 2.6 Choices in the public forms (Form options)
**Form options** holds every list visitors pick from: volunteer areas of service and availability, contact
topics, partnership types and interests.
* **Add a choice:** Add form option → pick the list, type the label (what visitors see) and a short code
  (lowercase, e.g. `prison-ministry`). The code can never change later; the label can.
* **Rename:** edit the label. Old submissions show the new name too.
* **Remove:** untick **Active**. It disappears from the form but older submissions keep their label.
  Options cannot be deleted, and the last active option of a list cannot be switched off.
* **Order:** lower numbers appear first.

---

## 3. Founder / Super Admin
*Everything, including users, site settings, giving settings and the audit log.*

### 3.1 Adding a staff member
1. **Users → Add user**: email, full name, a temporary password (12+ characters, mixed).
2. Save, then on the next screen tick **Roles** (one or more) and, for Branch Coordinators, choose their
   **Branch**; for Departmental Heads, their **Department**.
3. Give the password to the person **in person or by phone**, never by email, and ask them to sign in and
   set up the authenticator straight away (1.1).
4. To remove access: untick **Active** (keeps history). Do not share accounts between people.

Roles: **Secretary**, **Finance & Admin**, **Programs & Events**, **Media & Communications**, **Branch
Coordinator** (own branch only), **Departmental Heads** (own department only), **Founder**.

### 3.2 Site settings
**Site settings** holds the ministry name, tagline, vision, mission, About text, public email/phone, WhatsApp
number (for the floating chat button), address, footer, the **notification email** (where "new submission"
alerts go), analytics and the **data retention** periods. Social media links are under **Social links**.

### 3.3 Privacy policy, terms and extra pages
**Pages → Privacy policy / Terms**. Have them reviewed before launch, and update **Last reviewed**.
The privacy policy is a draft: complete the items in [square brackets] (legal name, minimum age, reply
time, provider names) and remove the "Draft" heading. Below your text, the page **automatically** lists the
cookies the site uses and the current retention periods from Site settings, so those facts are always
true; you do not need to write them yourself. The site uses only strictly necessary, browser-session
cookies, so no cookie banner is needed. If you switch on visitor statistics (Site settings > Analytics),
a consent question appears and visitors can change their answer with **Privacy choices** in the footer.
To add another page (e.g. "Statement of faith"): **Pages → Add page**, tick **Published** and
**Show in footer**. It appears at `/pages/<slug>/` and in the footer.

### 3.3a Logos and ministry name
**Site settings → Identity**: **Logo** (for light backgrounds, the header) and **Logo on dark background**
(footer, home page hero, link previews on WhatsApp/Facebook). PNG with a transparent background works
best. Leave empty to keep the built-in logos. The header wordmark is the **Ministry name**; its last word
is shown in flame orange.

### 3.4 Someone asks to see or delete their data
This needs the person who runs the computer/server (see README → *Maintenance commands*):
`manage.py personal_data export --email …` or `… erase --email … --yes`. Gifts are kept for the accounts
but the donor's name and contact details are removed.

### 3.5 Audit log
**Audit log** shows who signed in, viewed, exported, changed or deleted sensitive records. It cannot be
edited or deleted by anyone. Check it monthly, and immediately if something looks wrong
(`docs/INCIDENT_RESPONSE.md`).

### 3.6 Adding a branch or a new country
**Countries → Add** (if new), then **Branches → Add**: name, country, city, description, activities, meeting
times, contact details, photo, *Published*. It appears on the Branches page automatically. No developer is
needed.

---

## 4. Programs & Events
*Programmes, events and event registrations.*

### 4.1 Creating an event
1. **Events → Add event**: title, summary, description, start and end, venue/address, branch (empty =
   ministry-wide), programme, poster with alt text.
2. To take registrations: tick **Registration open**, optionally set a **deadline** and a **capacity**
   (empty = unlimited). The form closes by itself when the event is full, the deadline passes or the
   event ends.
3. Tick **Published** and save.

Past events move to "Past events" automatically.

### 4.2 Seeing who registered
**Event registrations** → filter by event on the right. Each person can register once per event (same
email). Mark people as cancelled to free their seats. Export only when needed (2.2).

### 4.3 Programmes
**Programmes → Add**: title, summary, body, icon, image, order (lower numbers appear first).

---

## 5. Media & Communications
*Gallery, sermons and resources, news, social links, newsletter list, home page hero slides and partner logos.*

### 5.0 Page headings and wording (Page text)
**Page text** lists every heading on the site: each page's header (eyebrow, heading, intro), the home page
hero and section titles, the three home cards, the "Be part of what God is rebuilding" band and the footer
newsletter blurb. Edit and save; the change appears within a few minutes.
* **Highlight** is only used by the home hero (the second line in flame colours). The "Home: hero" text
  only shows when **no hero slide** is switched on (see 5.7).
* **SEO title / description** change what Google and browser tabs show for that page.
* The headings above the sliders (Testimonies, Our partners, About page "Our leadership") are here too.
* The Give and Partner page intros come from **Giving settings** when Finance fills them in; otherwise
  from Page text.

### 5.1 News
**News posts → Add**: title, kind (news, announcement, report, testimony), summary, body, image + alt text.
* **Draft**: hidden. **Published**: visible now. **Scheduled**: set **Publish at** and it appears by itself
  at that time.

### 5.2 Photo albums
**Albums → Add**: title, description, date, branch/event, cover image. Save, then add **Photos** below (each
with alt text). Only publish photos of people who agreed to it; be especially careful with children.
On the album page the photos appear as a slider with thumbnails and a full-screen viewer. The **Order**
number on each photo sets its position (lower first); a **caption** shows under the photo.

### 5.3 Videos
Upload the video to the ministry's YouTube channel, then **Videos → Add** and paste the YouTube link. The
site loads YouTube only when a visitor presses play (faster, more private).

### 5.4 Sermons, devotionals, study material
**Resources → Add**: kind, title, speaker, date, scripture, summary/notes, YouTube link and/or MP3 (up to
60 MB) and/or PDF (up to 20 MB). Group a sermon series with **Series**, and topics with **Resource
categories**.

### 5.5 Testimonies
**Testimonies → Add**. Tick **Consent confirmed** only when the person agreed in writing.
* **Name shown**: the website shows **initials** (e.g. "M. K.") by default, or the **first name** if you
  choose it. The **full name** is only shown when you also tick **Consent to show full name**, which you
  should only do when the person explicitly agreed to it in writing. Leave the name blank for "Anonymous".
* **Approved**: a testimony appears on the website (home page slider and Testimonies page) only when it is
  **Approved** AND **Published** AND consent is confirmed. Read it through before approving.
* The list shows a column **Shown on the website as**: check it before publishing.

### 5.6 Newsletter subscribers
People join with double opt-in (they confirm by email). You cannot add people by hand; that protects the
ministry from spam complaints and respects privacy. **Export** gives confirmed subscribers only. Every
newsletter you send must include the unsubscribe link.

### 5.7 Home page hero slides
The large banner at the top of the home page is a slideshow of **Hero slides** (up to 5). Only Media &
Communications and the Founder can change them.

**Add a slide**
1. **Hero slides → Add hero slide**.
2. **Title**: the big heading, short (under 60 characters). **Subtitle**: one or two sentences.
3. **Image**: a landscape photo, **1920 x 900 pixels** is ideal (JPG, PNG or WebP). A dark shade is added
   automatically so white text stays readable; keep the important part of the photo on the **right**,
   because the text sits on the left. Fill in **Image alt** to describe the photo for blind visitors. No
   photo? Leave it empty: the slide uses the dark flame background with the logo.
4. **Button text** (e.g. Give, Volunteer, Register, Watch) and **Button link**. The link must be a page of
   this website starting with **/** (for example `/give/`, `/get-involved/`, `/events/`, `/resources/`) or
   a full secure address starting with **https://**. Anything else is refused.
5. Tick **Show scripture** to add Acts 15:16 (from Site settings) under the text.
6. The **Live preview** at the top changes as you type or choose a photo. Press **Save**.

**Reorder slides**: in the **Hero slides** list, change the numbers in the **Order** column (lower shows
first, e.g. 10, 20, 30) and press **Save** at the bottom of the list. Leave gaps (10, 20, 30) so a new slide
can go in between later.

**Hide or schedule a slide**: untick **Is active** to hide it without deleting it. **Start at** / **End at**
show a slide only between two dates (e.g. a conference banner that disappears after the event). The
**Status** column says Showing, Scheduled, Ended or Switched off.

The first slide ("Rebuilding Lives. Reviving Generations." with Acts 15:16) was created for you; edit it
rather than deleting it. If more than 5 slides are active, only the first 5 show and the list warns you. The
slideshow moves every 6 seconds, stops when a visitor hovers, touches or uses the keyboard, has a pause
button, and never moves for visitors who have asked their device to reduce motion.

### 5.8 Other sliders on the website (nothing to set up)
These fill themselves from what is already published:
* **Home**: programmes marked "featured", upcoming published events (with a Register button when
  registration is open), approved testimonies, every published branch (new branches appear
  automatically), and the latest news.
* **About**: confirmed and published leaders.
* **Albums**: the photos of the album (see 5.2).

**Image sizes** for cards in these sliders (events, news, programmes, branches): **1200 x 800 pixels**
(landscape, 3:2). Larger photos are fine; the website makes smaller copies automatically and removes hidden
location data from every photo.

### 5.9 Partners and supporters logo strip
**Partners → Add**: name, logo (PNG with a transparent background, at least 400 pixels wide), optional
website (must start with https://), order. Tick **Is published** only with the partner's permission to show
their logo. The strip appears on the home page only when at least one partner is published; it scrolls
slowly, pauses on hover and has a pause button.

---

## 6. Finance & Admin
*Giving settings, giving categories, current needs, donations, partnership enquiries.*

### 6.1 Bank and mobile-money details
**Giving settings**: account name, bank, account number, SWIFT, branch, currency and instructions; mobile
money instructions. They appear on the Give and Partner pages **only** when *enabled* and complete. These
details are stored encrypted and must **never** be put anywhere else (documents in the code, emails to
developers, chat).

Before saving new bank details, confirm them with the bank **by phone**. Fraudsters often send "updated
bank details" emails.

### 6.2 Confirming gifts
Donors who give by bank transfer fill in "I have given" (a pledge). Nothing is confirmed until money arrives.
1. Check the bank statement.
2. **Donations** → find the pledge (filter *Pledged*, or search the exact donor email).
3. Tick it → **"Confirm selected gifts as received (issues receipt)"** → **Go**. A receipt number is created
   and the donor is emailed a receipt if they gave an email.

Never write a donor's personal details in **Finance notes**.

### 6.3 Categories and current needs
**Giving categories** (e.g. Youth revival conferences, Evangelism and missions) and **Current needs** (title,
target, amount raised) appear on the Give and Partner pages.

### 6.4 Online card / mobile-money gateway
Not active yet. See `docs/GIVING_GATEWAYS.md`. Leave **Gateway enabled** off until a developer has finished
the integration.

### 6.5 Partnership enquiries
Handled like other submissions (2.1).

---

## 7. Branch Coordinators
You only see **your branch**: its events, event registrations, volunteer applications, news and albums.
* Update your branch page: **Branches → your branch** (description, activities, meeting times, contacts,
  photo).
* Add events and news for your branch (sections 4 and 5). The branch is filled in for you.
* Follow up volunteers who chose your branch (2.1).

## 8. Departmental Heads
You see your **department's** programmes, events, registrations and news. Create events and news as in
sections 4 and 5; your department is filled in for you.

---

## 9. Getting help
Content questions: the Founder. Technical problems: the website administrator. **Anything that looks like
a break-in** (unknown sign-in alert, strange changes, a lost phone with no backup codes): tell the Founder
immediately and follow `docs/INCIDENT_RESPONSE.md`.
