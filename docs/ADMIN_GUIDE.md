# Staff guide: the staff portal and the website

This guide is for ministry staff. You do not need any technical knowledge. Each section says **who** can do
the task. If a menu item in this guide is missing for you, your role does not include it. That is on
purpose: everyone only sees what they need.

There are two places to work:

* **The staff portal** (Part B, sections 10 to 21): where you land after signing in. Each department has its
  own dashboard and its own records (members, ledger, purchases, campaigns, classes, projects…).
* **Website content** (Part A, sections 1 to 9): news, events, photos, page wording and similar public content,
  edited in the admin. Open it from **Website content (admin)** at the bottom of the portal menu.

Part A: everyone, and website content

---

## 1. Everyone

### 1.1 Signing in
1. Open the link in your **invitation email** (only the Super Admin can create accounts; nobody can sign
   up). Choose your own password. Later, sign in at the staff sign-in page (it is **not** `/admin/`).
2. Enter your email and password.
3. **First time only:** you will see a QR code. Install an authenticator app on your phone (Google
   Authenticator, Microsoft Authenticator or Authy), tap "add account", scan the code, then type the 6-digit
   number the app shows. You will then see **10 backup codes**: write them on paper and keep them somewhere
   safe. Each works once if you lose your phone.
4. Every other time: after your password, type the current 6-digit number from the app.

Use the invitation link **within 48 hours**: it works only once. If it has expired, ask the Super Admin
for a new one.

### 1.2 Rules for every staff member
* Use a long password (at least 12 characters) that you use **nowhere else**. A password manager helps.
* Never share your account, password, phone codes or backup codes, not even with the Founder.
* Lock your computer when you step away. Sign out on shared computers.
* The site signs you out after 2 hours without activity, and when you close the browser.
* After 5 wrong passwords your account is locked for one hour. Ask the Super Admin if you are locked out.
* Accounts not used for 60 days are flagged, and after 90 days they are switched off automatically.
* Never download prayer requests or volunteer lists to a personal or shared computer. Never forward them by
  email or WhatsApp.
* Be suspicious of any email asking you to sign in "urgently" or send codes. The website will never ask for
  your authenticator code by email.
* Everything you open, change, export or delete is recorded in the audit log.

### 1.3 Lost phone or backup codes
Ask the Super Admin to use **Accounts & security → Staff accounts → your name → "Reset two-step sign-in"**
(see 21). At your next sign-in you will scan a new QR code. If you still have your phone, press **New backup
codes** at the top right of the admin to get a fresh set; the old ones stop working immediately.

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

## 2. Membership Administration: website content
*Contacts, prayer requests, general volunteers, events, news, leadership (formerly the "Secretary" role).*

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
Staff accounts are created **only in the staff portal** (section 21), never in the admin (the admin's user
pages are read-only). Roles are the seven departments (member or head), **Branch Coordinator**, **Executive
Leadership**, **Technical Team (Website Administration)** and **Super Admin (Founder)**.

### 3.2 Site settings and Site content
There are two separate screens, so each team only sees its own:
* **Site settings** (Super Admin only): the **notification email** (where "new submission" alerts go;
  giving, partnership and other finance enquiries go to the Finance heads instead), analytics, the **data
  retention** periods, and **Approval rules > Vision and mission approval required** (on by default).
* **Site content** (Technical Team and Super Admin): ministry name, tagline, logos, favicon, scripture, About
  text, public email/phone, WhatsApp number (for the floating chat button), address and footer. The Vision and
  Mission are shown there but changed only in the portal (section 5A.3).

Bank details are in neither: see section 6.1.

### 3.2a Upload limits
**Upload limits** (Super Admin only): for each kind of upload (hero photo, gallery photo, receipt...) you can
change the maximum size, the minimum width or (background video) the maximum length. Leave a box empty to keep
the built-in rule shown on the screen. The accepted file formats cannot be changed here, on purpose.

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
**Site content → Identity**: **Logo** (for light backgrounds, the header) and **Logo on dark background**
(footer, home page hero, link previews on WhatsApp/Facebook), and **Favicon** (square PNG). PNG or WebP with a
transparent background, up to 2 MB. Leave empty to keep the built-in logos. The header wordmark is the **Ministry name**; its last word
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

## 4. Missions & Outreach: website content
*Events and event registrations (formerly the "Programs & Events" role); activities are managed by the Technical Team.*

### 4.1 Creating an event
1. **Events → Add event**: title, summary, description, start and end, venue/address, branch (empty =
   ministry-wide), activity, poster with alt text.
2. To take registrations: tick **Registration open**, optionally set a **deadline** and a **capacity**
   (empty = unlimited). The form closes by itself when the event is full, the deadline passes or the
   event ends.
3. Tick **Published** and save.

Past events move to "Past events" automatically.

### 4.2 Seeing who registered
**Event registrations** → filter by event on the right. Each person can register once per event (same
email). Mark people as cancelled to free their seats. Export only when needed (2.2).

### 4.3 Activities
The ministry's activities (School Outreach Programme, Open-Air Crusades, Revival Programme...) are website
content managed by the Technical Team (section 5A.4). When you create an event or an outreach campaign, choose
its **Activity** so it appears on that activity's page and on your dashboard.

---

## 5. Media & Communications: website content
Most media work can also be done in the staff portal (section 14): albums, videos, testimonies and hero
slides are the same records in both places.
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
3. **Background**: *Theme colour* (the dark flame background with the logo), *Photo* or *Video*. A photo
   must be at least **1600 pixels wide** (1920 x 900 is ideal; JPEG, PNG or WebP, up to 5 MB). Set the
   **focal point** (which part stays visible on phones) and the **dark overlay** (0-80 %) so the text stays
   readable; the **Readability** line warns if the text would be hard to read. For a video see section 5A.2.
   Fill in **Image alt** to describe the photo for blind visitors. Empty or missing? The slide uses the theme
   colour.
4. Up to two buttons: **label** (e.g. Give, Volunteer, Register, Watch) and **link**. The link must be a
   page of this website starting with **/** (for example `/give/`, `/get-involved/`, `/events/`) or a full
   secure address starting with **https://**. Anything else is refused. Choose **text alignment** (left or
   centre) and **text colour** (light text for dark backgrounds, dark text for light ones).
5. Tick **Show scripture** to add Acts 15:16 (from Site settings) under the text.
6. The **Live preview** at the top changes as you type or choose a photo. To check a new slide before
   visitors see it: untick **Is active**, press **Save**, then **Open a full-size preview**; tick **Is active**
   when it looks right. Every save is kept: **Website > Changes and rollback** in the portal puts an earlier
   version back.

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
* **Home**: activities marked "featured" (one carousel per category), upcoming published events (with a Register button when
  registration is open), approved testimonies, every published branch (new branches appear
  automatically), and the latest news.
* **About**: confirmed and published leaders.
* **Albums**: the photos of the album (see 5.2).

**Image sizes** for cards in these sliders (events, news, activities, branches): **1200 x 800 pixels**
(landscape, 3:2). Larger photos are fine; the website makes smaller copies automatically and removes hidden
location data from every photo.

### 5.9 Partners and supporters logo strip
**Partners → Add**: name, logo (PNG with a transparent background, at least 400 pixels wide), optional
website (must start with https://), order. Tick **Is published** only with the partner's permission to show
their logo. The strip appears on the home page only when at least one partner is published; it scrolls
slowly, pauses on hover and has a pause button.

---

## 5A. Technical Team (Website Administration)
*The website's wording, pictures and layout. You never see money, donors, members, prayer requests,
discipleship records or staff accounts, and you cannot change bank details.*

### 5A.1 Your dashboard
After signing in you land on **Website dashboard** (portal). It shows:
* **Drafts awaiting publish**: a hero draft not yet published, Vision/Mission changes, switched-off slides.
* **Pages needing updates**: pages never reviewed, reviewed more than a year ago, still marked "Draft", and
  activities without a photo. Click one to open it.
* **Broken links and missing images**: buttons pointing to a page that does not exist, unsafe links, photos
  whose file is missing.
* **Site health**: whether the website and database are running, the **last backup** (a warning after 36 hours
  without a successful backup: tell the Super Admin) and whether the hero text is readable.
* **Upload storage**: how much space the website's photos and files use.
* **Recent changes**: who changed what and when.

### 5A.2 The home page hero (big banner)
**Website > Home page hero**. You always edit a **draft**; visitors keep seeing the live hero until you
publish.
1. Write the **headline**, **sub-headline** and up to two **buttons** (label + link starting with / or https://).
2. Choose **text alignment** and **text colour** (light or dark).
3. Choose the **background**: *Theme colour* (default, brand black with the flame glow), *Photo* or *Video*.
   * Photo: at least 1600 pixels wide, up to 5 MB. Move the **focal point** sliders and the **dark overlay**.
   * Video: MP4 (H.264) or WebM, **silent** (no sound track), at most **15 seconds** and **15 MB**; best is a
     loop of **10 seconds or less, 1080p, under 10 MB**. A **poster image is required**: visitors on a slow
     connection, with data saver on, or who prefer less motion see the poster instead, and every visitor
     sees it while the video loads.
4. The **live preview** on the right changes as you type, and says whether the text is readable (WCAG AA). If
   it warns, darken the overlay or change the text colour.
5. **Save draft**, then **Preview the draft full size** to see it on the real page.
6. **Publish draft** when it is right. **Revert to previous** puts the previous live hero back in one click.
   **Discard draft** starts again from what is live.
If no photo or video is set (or a file is missing), the hero simply uses the theme colour.
When hero **slides** are switched on, the home page shows the slider instead (section 5.7).

### 5A.3 Vision and Mission
**Website > Vision and mission**. The wording appears on the home page, the About page, the footer and in
search results, all from this one place.
1. Choose Vision or Mission, type the new wording **exactly**, give a reason, **Save draft and preview**.
2. Check the preview, then **Submit for approval**.
3. The **Super Admin or the Executive Director** approves (they confirm with their password and code). You
   cannot approve your own change.
4. After approval, press **Publish**. The new wording is live everywhere at once.
The history lists every published version; **Restore this version** sends an earlier wording for approval.
(If the Super Admin has switched approval off, you publish straight after the preview.)

### 5A.4 Activities
**Admin > Activities** and **Activity categories**. The four categories (Charitable and Humanitarian Services,
Evangelism and Missions, Discipleship, Revival Programme) each have their activities. For each activity: title,
summary, text, photo (JPEG/PNG/WebP up to 3 MB), **schedule** ("Every last Friday, 6 pm"), **branches** (leave
empty for all), the **Get involved** button (empty = the volunteer form), order, published, featured (home
page) and SEO text. A new activity or category needs no developer. The **department** an activity feeds (staff
dashboards) is set by the Super Admin only. Events linked to an activity appear on its page automatically.

### 5A.5 Everything else you manage
* **Site content**: ministry name, logos, favicon, About text, public email, phone, WhatsApp, address, footer.
* **Branches**: each branch's address, phone and email.
* **Social links**, **Pages** (About, Privacy, Terms and others; update **Last reviewed**), **Page text**
  (headings and SEO titles/descriptions of every page), **Hero slides**, **Partners**, **Leaders** (the
  leadership page) and the **gallery layout** (album order, cover and publishing).
* Photos: JPEG, PNG or WebP; location data is removed automatically. SVG files, web pages and programs are
  always refused.

### 5A.6 Undo a mistake
**Website > Changes and rollback** lists every change. **Restore** puts that item back exactly as it was then
(photo included); a deleted item can be brought back with **Undelete**. Restoring is itself recorded, so it can
be undone too.

---

## 6. Finance & Resource Mobilization: giving settings
*Giving settings, giving categories, current needs (formerly the "Finance & Admin" role). Confirming gifts and
partnership registrations are now done in the staff portal (section 12).*

### 6.1 Bank and mobile-money details (two-person rule)
Bank and mobile-money details are changed **only** in the portal: **Bank details** (Finance head, Founder,
Executive Director and Super Admin; nobody else can open it, not even other Finance members or the Technical
Team). They are not in the admin any more.
1. **Finance head**: confirm the new details with the bank **by phone** (a number you already know, never one
   from an email). Then **Propose a change**; you are asked for your password and authenticator code. Fill in
   the details and the reason. The change is saved as **pending**: nothing changes on the website yet.
2. An email alert goes to the Finance heads and the Founder/Super Admin. It shows only the **last four digits**
   of the new account number. If you did not expect it, tell the Super Admin immediately.
3. **Founder or Executive Director** (never the person who proposed it): open the pending change, compare each
   line (changed lines are marked), check with the bank yourself, and **Confirm and publish** (password and
   code again) or **Reject** with a reason.
4. Only after confirmation do donors see the new details, with a **Last verified** date on the Give page.
Every change, rejection and cancellation is kept in **History**. Only one change can be pending at a time.
The details are stored encrypted and must **never** be put anywhere else (code, emails to developers, chat).

### 6.2 Confirming gifts
Donors who give by bank transfer fill in "I have given" (a pledge). Nothing is confirmed until money arrives.
1. Check the bank statement.
2. In the portal: **Finance → Website donations & pledges** → filter *Pledged* → open it → **Confirm
   received**. A receipt number is created, the donor is emailed a receipt if they gave an email, and an
   income entry is created in the ledger for **someone else** to approve (section 12).

Never write a donor's personal details in **Finance notes**.

### 6.3 Categories and current needs
**Giving categories** (e.g. Youth revival conferences, Evangelism and missions) and **Current needs** (title,
target, amount raised) appear on the Give and Partner pages.

### 6.4 Online card / mobile-money gateway
Not active yet. See `docs/GIVING_GATEWAYS.md`. Leave **Gateway enabled** off until a developer has finished
the integration.

### 6.5 Partnership registrations
Arrive in the portal under **Finance → Partnership registrations** and are added to the donor pipeline as
prospects automatically (section 12).

### 6.6 Giving and partnership enquiries
On the contact form visitors choose a **Subject**: General, Giving and finance, or Partnership. Giving and
partnership messages go **only** to Finance: **Finance → Giving and partnership enquiries** in the portal, and
the "new message" alert goes to the Finance heads (not to the general inbox). Membership never sees them. The
same is true for partnership registrations, pledges and finance-volunteer applications.

---

## 7. Branch Coordinators: website content
In the admin you only see **your branch**: its events, event registrations, volunteer applications, news and
albums. (Your portal access is in section 19.)
* Update your branch page: **Branches → your branch** (description, activities, meeting times, contacts,
  photo).
* Add events and news for your branch (sections 4 and 5). The branch is filled in for you.
* Follow up volunteers who chose your branch (2.1).

## 8. Department heads
The old "Departmental Heads" role was retired: a head is now marked per department by the Super Admin, and
heads work in the staff portal (Part B). Website content follows the department's role above.

---

## 9. Getting help (website and portal)
Content questions: the Founder. Technical problems: the website administrator. **Anything that looks like
a break-in** (unknown sign-in alert, strange changes, a lost phone with no backup codes): tell the Founder
immediately and follow `docs/INCIDENT_RESPONSE.md`.


---

# Part B: the staff portal

## 10. The staff portal: for everyone

**Where you land.** After signing in you go straight to *your* department's dashboard. The Founder and
Executive Leadership land on the **Executive overview**. If you belong to several departments, all of them
are in the menu. If the menu is empty, the Super Admin has not given you a department yet.

**The menu** (left on a computer, the orange **Menu** button on a phone) shows only your departments and the
screens your role allows. **Head** means you are the head of that department; **Branch** means you see it
as a Branch Coordinator (your branch only).

**Every dashboard has the same parts:**
* **Filters** at the top: a date range (the last 12 months by default) and a branch. Changing them updates
  the page.
* **Key figures** (the boxes), **charts** (point at a bar or dot to see the exact number; "Show data table"
  lists the numbers), **Needs attention** (late, overdue or waiting items, each with a link), **Recent
  activity** and buttons for the most common tasks.
* Status labels always come with a symbol: ✓ on track, ! needs attention, ✕ behind/overdue.
* **Export** (heads only): CSV for a spreadsheet, or **Printable / PDF** (then *Print → Save as PDF* in the
  browser). Every export is recorded in the audit log, so export only what you need.

**Lists and records.** Every list has filters and, where possible, a search box (names are encrypted, so
search works on numbers, titles and similar plain fields). Open a record to see its details, related records
(for example a member's welfare cases) and the next steps you may take. **Add**, **Edit** and **Delete**
appear only when your role allows them. Deleting usually needs the head.

**Files** (receipts, permits, member documents, field photos) are private: they are never on the public
website and can only be downloaded from the portal by people allowed to see that record. Each download is
recorded.

**Our budget.** Every department has **Our budget** in its menu: your department's budget lines and what has
been spent this year. It shows totals only; the transactions themselves are kept by Finance.

**Asking another department for something**
* *A purchase* (Logistics): **Logistics → Purchase requests → Add** (you only see your own department's
  requests). Follow it through quotations, Finance budget confirmation, approval and delivery.
* *A poster, banner or flyer* (Media): **Media & Communications → Design requests → Add**.

**Personal data rules in the portal**
* Under-18s are visible only to the head of Membership (or Discipleship) and the Founder.
* Pastoral notes are seen only by the person's assigned mentor, the Discipleship head and the Founder.
* Ledgers and donors are seen only by Finance and the Founder.
* Lists and records of personal data are recorded in the audit log every time they are opened.

## 11. Membership Administration
*Member register, admission, participation, welfare and internal communications.*

* **New registrations** from the website form arrive in **Member register** as *Application received* (you
  also get an email alert without details). Open one and use the buttons in order: **Start review** →
  **Approve** or **Do not accept** (head only; a short private reason is required for "do not accept") →
  **Start orientation** → **Start integration** → **Mark active**. Later: **Mark inactive** or **Mark
  transferred** (fill in "Transferred to" first). The applicant gets an email when you approve or decline; it
  never repeats what they wrote, nor your reason.
* **Member numbers** (RLM-000123) are given automatically on approval.
* **Under 18:** the form already asks for a parent or guardian. You cannot approve a child until the guardian's
  name, contact and consent are recorded. Only the head sees children's records.
* **Attendance:** **Activities & attendance → Add** (service, fellowship, meeting, class, outreach), then
  **Take attendance** and tick who was present. Each member's **engagement score** (0-100) is the share of
  their branch's activities in the last 90 days they attended, plus 10 if they currently serve somewhere.
* **Service records**, **welfare cases** and **documents** are added from a member's page. Welfare summaries
  are encrypted; write only what is needed to help.
* **Communications:** announcements, meeting minutes and the correspondence log (incoming and outgoing
  letters, with an optional scanned copy).
* **Messages to members** (head only to send): write the message, choose email or WhatsApp and the audience.
  Only members who ticked "send me ministry announcements" receive it, never under-18s, and each person gets
  their own email (nobody sees the other addresses). For WhatsApp the portal lists one link per person that
  opens WhatsApp with the message ready; you press send.
* **Dashboard:** members, active, new this month, pending approvals, retention, open welfare cases; charts by
  month, branch, gender and age band.

## 12. Finance & Resource Mobilization
*The most restricted department: only Finance and the Founder see ledgers and donors.*

**The golden rule: the person who records an entry can never approve it.**
1. **Income & expenditure ledger → Add**: kind, date, amount, department, budget line, category (expenditure)
   or source (income), description, payer/payee, voucher or receipt number, and a scan of the receipt.
2. Open it and press **Submit for approval**.
3. **Income:** someone else in Finance opens it and presses **Approve and post** (or **Reject**, with a reason
   that goes back to the recorder).
   **Expenditure (any payment, of any amount):** it waits for **executive approval** by the Founder, the
   Executive Director or the acting approver (see 12.1). Finance does not approve spending any more and there
   is no longer a "small amounts" threshold.
4. **Posted entries can never be edited or deleted.** If one is wrong, the head presses **Reverse
   (correct)**: a matching negative entry is created and must be approved by someone else; then record the
   correct entry.

**Budget:** **Annual budget** (head): one line per department, branch and purpose. A new line starts as a
**draft**: press **Submit for executive approval**; only approved lines count as budget. Approved lines cannot
be edited; changes go through a reallocation or supplementary budget at approval time (12.1). The dashboard shows budget vs
actual per department, burn rate (average monthly spending over the last three months, and how many months
the cash would last), cash position and income by source. Every department sees only its own totals in **Our
budget**.

**Gifts from the website:** **Website donations & pledges** → open a pledge → **Confirm received** once the
money is in the bank. This issues the receipt and creates an income entry for someone else to approve.

**Resource mobilization**
* **Partnership registrations** (website form) are added to **Donors, sponsors & partners** as *Prospects*
  automatically. Move each one through the stages: prospect → contacted → proposal sent → committed → support
  received (or lapsed). Set a **next step** and date; overdue ones appear under Needs attention.
* **Pledges** (what a partner committed, and what has arrived), **Grant opportunities** (with deadlines:
  anything due in 30 days is flagged) and **Appeals & proposals** (letters, proposals, partnership requests,
  donor reports, with the document).
* **Accountability report:** on a donor's page, **Accountability report** gives a printable summary of their
  commitments, what arrived and what was shared with them.
* **Purchases: budget confirmation:** purchases recommended by Logistics wait here. Open one, check the
  quotations and choose the requesting department's budget line, then **Confirm budget**.
* **Capital proposals** from Development arrive in **Appeals & proposals**.

### 12.1 Executive approval (Founder, Executive Director, acting approver)
**Everything that spends or commits money needs executive approval before it is paid or committed:**
expenditure entries (including project costs and reimbursements), purchase requests (after Finance has checked
the budget), outreach campaign and mission-trip budgets, event budgets, and new budget lines.
* Approvers open **Approvals** at the top of the menu (the number shows what is waiting). Open an item, read it,
  and press **Approve** or **Do not approve**. You are asked for your **password and an authenticator code**
  before the decision is saved. Every decision is kept permanently and the person who asked gets an email (it
  says only "approved" or "not approved", never amounts or details).
* **Nobody decides their own item.** If you recorded, requested or budget-checked something yourself, another
  approver must decide it.
* **UNBUDGETED** (black-on-gold label) means: no approved budget line, or more than what is left on the line
  after other approved commitments. To approve it you must write a **justification**. If Finance settings say
  "unbudgeted spending requires an adjustment", you must also choose a **reallocation** (move money from
  another approved line that has enough left) or a **supplementary budget**. Unbudgeted items are listed first
  and also appear on the Finance dashboard and the Executive overview.
* **Who approves:** the Super Admin sets this under **Accounts & security → Executive approvers**: the Founder,
  the Executive Director and, when the Founder travels, an **acting approver with start and end dates**. Each
  change asks for the Super Admin's password and code again. Until the list has anyone in it, the Super Admins
  approve.

### 12.2 Financial years
The financial year is **1 January to 31 December**. Every screen has a **Financial year** and **Period**
(quarter or month) filter. At year end the Finance head (or Super Admin) presses **Close year** under
**Financial years**: nothing can then be posted, changed or budgeted in that year. Only the Super Admin can
**Reopen** a closed year, with a reason and their password and code again.

### 12.3 Executive finance page
Executive Leadership, the Founder and Finance see **Executive finance**: income, spending, cash position,
outstanding pledges, approved budgets and budget vs actual per department and branch, with year/quarter/month
and branch filters. Click a department to see its **category totals**. It never shows individual entries,
donors, vouchers or receipts; those stay with Finance and the Founder.

**Finance volunteers (vetting):** applications from the website form. **Start reference check** → tick
*References checked* (Edit) and add notes → **Move to interview** → **Approve volunteer** or **Do not take
forward** (head). Approving a volunteer does **not** give them any access: only the Super Admin can create an
account, and should do so only after vetting.

## 13. Logistics & Procurement
* **Purchase requests** come from any department (or are raised by Logistics). Steps:
  1. The request is **submitted** (it gets a PR number).
  2. Logistics adds **at least three quotations** (on the request page, *Quotations → Add*).
  3. The page shows them **side by side, cheapest first**. Choose one and press **Recommend this supplier**.
     If it is not the cheapest, you must explain why.
  4. **Finance confirms the budget** (section 12).
  5. **Executive approval** (Founder, Executive Director or acting approver, section 12.1). If Finance found no
     budget line with enough money left, the request is marked **UNBUDGETED** and needs a written justification.
     Whoever asked for the purchase, or checked its budget, can never approve it.
  6. **Issue purchase order** (PO number), then **Record a delivery** when goods arrive (tick *complete* only
     when everything arrived in good condition), **Add to inventory** if needed, and **Close request**.
* **Supplier register** with a 1-5 rating; **Assets & inventory** (quantity, condition, location, custodian,
  maintenance interval); low stock (at or below the reorder level) and maintenance due within 14 days are
  flagged; **Check-in / check-out** records who borrowed what and when it is due back.
* **Event logistics plans**: one per conference, crusade, fellowship or outreach, with a checklist of
  transport, accommodation, feeding and equipment tasks; the dashboard shows how much of each checklist is done.
* **Dashboard:** open requests, waiting for Finance, waiting for approval, spending, late deliveries, low stock.

## 14. Media & Communications
* **Content calendar:** plan each post or article with its channel (website, Facebook, Instagram, TikTok,
  YouTube, WhatsApp) and move it through *idea → in production → in review → published*. Assign it to a
  team member. The dashboard compares published with planned.
* **Design requests:** any department can ask for posters, banners and flyers and follow its own requests;
  Media sets the status, assigns a designer and uploads the final file. Late requests are flagged.
* **Event coverage:** events in the next 30 days without a coverage plan are flagged. Add a plan with the
  photographer, videographer and live-stream choice.
* **Social reach (manual):** each month, type the followers, reach and engagement from each platform's own
  insights. The website uses no tracking scripts.
* **Media archive (public site):** photo albums and photos, videos, testimonies and the home page hero slides
  are managed here as well as in the admin (section 5).
* **Testimonies:** a testimony appears on the website only when consent is recorded, **"the person is 18 or
  over"** is ticked and the **Media head** presses **Approve for the website**. Testimonies of children are
  never published.

## 15. Missions & Outreach
* **Outreach campaigns:** crusades, open-air meetings, school/hospital/prison/community visits, door-to-door
  and mission trips, with the community, team, dates, budget request (ask Logistics for purchases), materials
  and status.
* **Field reports** after each campaign: people reached, decisions for Christ, challenges, testimonies
  (private) and photos (tick "people consented" only if identifiable people agreed).
* **New converts:** record each person who made a decision (name, phone, area, age band, consent to be
  contacted). **Every convert is handed to Discipleship automatically** for follow-up; the convert's page
  shows how far the follow-up has got. Under 18: a parent or guardian contact is required, and only the head
  sees the record.
* **Communities & locations:** target communities, schools, prisons and churches with their status and any
  expansion opportunity, plus contacts (pastors, chiefs, head teachers; encrypted).
* **Evangelism teams** with their members and volunteers; a team's page lists its campaigns (assignments).
* **Dashboard:** campaigns held, people reached, decisions, follow-up completion, communities engaged, and an
  **impact by location** table.

* **Budgets of campaigns and mission trips:** fill in *Budget request* and choose a budget line, then press
  **Submit budget for executive approval**. A campaign with a budget cannot be marked approved, in progress or
  completed until the budget is approved. What has actually been paid shows on the campaign (from the Finance
  ledger). Logistics does the same for **event budgets** on an event-logistics plan.

## 16. Discipleship
* **New-convert follow-up:** converts handed over by Missions. Assign a person and work through **Mark
  contacted → First visit done → Enrol in discipleship** (choose a class) **→ Milestone review → Follow-up
  completed**, or **Could not be reached**. A first contact is due within 7 days; late ones are flagged on
  your dashboard and on the Executive overview. If "Agreed to be contacted" says NO, do not contact them
  without consent.
* **Registrations (website):** the discipleship form. **Mark contacted**, then **Enrol** (choose a class) or
  **Not taken forward**. Under-18s need the guardian's contact and consent before enrolment.
* **Disciples:** everyone in the programme, with their stage, the growth areas they chose and their
  **assigned mentor**.
* **Classes / cohorts:** schedule, facilitator, curriculum; **Sessions → Take attendance**.
* **Curriculum & Bible study materials:** upload the PDF or link a published sermon or devotional.
* **Mentorship pairings** and **accountability check-ins** (encrypted; seen only by the mentor, the head and
  the Founder). Pairings without a check-in for 30 days are flagged.
* **Growth assessments:** score the seven areas from the form (biblical knowledge, prayer and intercession,
  spiritual gifts, Christian character, evangelism, leadership and ministry, spiritual maturity) from 1 to 5.
* **Leader development:** identified → in training → serving as apprentice → commissioned.
* **Pastoral notes** are the most sensitive records in the system: only the person's **assigned mentor**, the
  **Discipleship head** and the **Founder** can read them; each opening is recorded; they can never be
  exported; only the author can edit a note.

## 17. Development & Infrastructure
*Project money is kept in the Finance ledger only (one set of books).*
* Each project needs a **budget line** (its cost centre) created by Finance and approved by the executive;
  choose it on the project. The project's budget is that line.
* **Project costs (Finance ledger) → Add**: project, date, amount, description, reference. Then **Submit for
  approval**: it goes to executive approval like every payment. Finance sees exactly the same entry.
* The project page shows **budget, committed (waiting or approved but not yet paid), spent, remaining**, and
  money spent next to milestones done. The dashboard warns about **overspent** projects, **UNBUDGETED** costs,
  **money ahead of progress** and projects **without a budget line**.

* **Project register** (offices, conference halls, hostels, training centres, worship facilities): phase,
  budget, funding secured, dates, project manager and contractors. On a project's page add **milestones**,
  **costs**, **documents** (designs, bills of quantities, permits, contracts: private files), **site visits**
  (date, progress %, summary, quality concerns, photos) and **risks and issues**.
* The dashboard shows projects by stage, budget spent per project, the **funding gap**, overdue milestones and
  a **project timeline** (grey bar = planned dates, dark part = progress seen on site, black line = today).
* **Property & land register** (title references are encrypted, title documents are private files) and
  **maintenance requests & schedule** (urgent safety issues are flagged to the Founder).
* **Contractors & partners:** contractors, architects, engineers, surveyors and development partners.
* **Capital proposals:** write the proposal for a project; the head presses **Send to Finance for
  fundraising** and it appears in Finance's appeals & proposals.

## 18. Targets and monthly reports (monitoring & evaluation)
* **Performance targets** (top of the menu) are set by **leadership** (the Founder / Super Admin and Executive
  Leadership). Each target has a **category** (evangelism, discipleship, youth fellowships, membership,
  partnerships, missions, finance, development, media, prayer), an owner department, a unit, a **financial
  year**, a **branch** (or all branches) and an **annual target**, which is split into **monthly targets**
  automatically (evenly; percentages stay the same every month). Change any month or the annual figure on the
  target's page; a **reason is required** and every change is listed under *Change history* (who, old, new,
  why).
* **Importing many targets:** *Import CSV* → download the template, fill one row per target, upload, check the
  preview, then **Import these targets**. If any row is wrong, nothing is imported and every problem is listed.
* **Monthly actuals:** department members open a target and **Record a monthly actual** (only for months that
  have started, and only for their own branch if their role is branch-limited).
* **Colours:** Green = 90% of target or better, Amber = 70-89%, Red = below 70% (for "lower is better" targets
  the percentage is turned round). A month's actual is **overdue** if it is still missing on the 10th of the next
  month. The Executive overview shows every category and the overdue list.
* `manage.py seed_indicators --demo` creates **fake sample targets** for a demonstration only (named
  "[DEMO] ..."); remove them with `manage.py seed_indicators --remove` before real use.
* **Automatic values:** an indicator can be linked to a dashboard figure ("auto source"). The suggested ones
  already are; the codes are listed under each dashboard box in the CSV export (e.g. `active_members`,
  `decisions`, `follow_up_rate`, `late_deliveries`, `milestones_overdue`).
* **Monthly report** (heads): on the dashboard, **Generate report** for a month. It saves the dashboard
  figures and the target values for that month. Add *highlights*, *challenges*, *plans* and *support needed*
  (Edit), then **Submit to the Founder**. It is due by the **10th of the following month**; after that it shows
  as overdue on the Executive overview.
* The **Founder** reviews submitted reports: **Mark as reviewed** or **Return for changes** with a comment
  (the department can then edit and resubmit).

## 19. Branch Coordinators in the portal
You see **Membership**, **Missions & Outreach** and **Discipleship**, always limited to **your branch**:
members (read only), activities and attendance, campaigns, field reports and new converts (you can add these),
classes and attendance. You never see under-18s, pastoral notes, other branches, Finance or exports. If your
account has no branch, you see nothing that belongs to a branch: ask the Super Admin.

## 20. Executive overview (Founder and Executive Leadership)
One page for all departments: **flags across the ministry** (over-budget departments, late deliveries,
converts not contacted on time, overdue building milestones, urgent maintenance, applications waiting too
long), a summary card per department, **pending approvals**, **cross-department handoffs** (Missions →
Discipleship, Logistics → Finance, design requests to Media, capital proposals to Finance), the state of last
month's reports and progress against every department's targets. It shows **totals only**. Executive
Leadership can open a department only if they also belong to it; the Founder can open everything.

## 20a. Printing reports
Every report has a **Print / Save as PDF** button: department dashboards, the Executive overview, Executive
finance, performance targets, monthly department reports, and lists such as the member register, finance
volunteers or purchase orders. The printout is an A4 page with the logo, title, department, branch, period and
financial year, who printed it and when, page numbers and an **approval box** (Prepared / Reviewed / Approved
by, with name, signature and date). Choose *Save as PDF* in the print window to keep a file.
* Reports with personal or financial information are marked **CONFIDENTIAL** at the bottom: keep them safe and
  shred them when done.
* Printing a list of people needs the same permission as exporting it (usually the department head), and
  every print is recorded in the audit log.

## 20b. Applications: what happens to them (retention)
This covers the **membership, discipleship, partnership and finance-volunteer** applications from the website.
* Each application is **pending**, **successful** or **unsuccessful**. The application screen shows its
  **retention deadline**.
* **Successful:** the person moves into the proper record (member register, discipleship class, partner list,
  vetted volunteer list). For discipleship and partnership the application is then emptied and keeps only a
  reference such as "Disciple #12". (Partnership: the Finance head presses **Taken forward** or **Not taken
  forward**.)
* **Unsuccessful:** deleted automatically **365 days after the decision** (under-18s: **90 days**), including
  any documents; only anonymous counts (type, branch, month, outcome) are kept. The periods are in **Site
  settings** (Super Admin).
* On the **1st of each month** department heads get an email with how many of their applications will be
  deleted in the next 30 days (no names). If one must be kept (for example a legal dispute), ask the Super
  Admin for a **legal hold** before the deadline.
* **Super Admin → Accounts & security → Application retention:** see what *would* be deleted now (a dry run
  that deletes nothing), place or lift **legal holds**, run the deletion now, and **delete an application early
  when the person asks** (password and code required; write down how the request was checked).
* Applications from **under-18s** are visible only to the department head and the Founder.
* If the privacy policy page has been edited so much that it no longer has a "How long we keep it" heading,
  add the "Applications" section yourself (text in `core/migrations/0012_privacy_policy_applications.py`).

## 21. How the Super Admin creates and manages accounts
*Only the Super Admin (the Founder, at most two people) can create, activate, change, deactivate or delete
staff accounts. Nobody can sign up on the website, and department heads cannot add or change anyone.*

Open **Accounts & security** in the portal menu. Every change asks for **your password and a fresh code from
your authenticator app** first (it stays unlocked for 5 minutes). You can never change your own account or
roles: another Super Admin must.

**Invite a new staff member**
1. **Invite a staff member**: full name, email, and for each department *No role / Member / Head*. Tick
   **Branch Coordinator** (and choose the branch), **Executive Leadership** or **Super Admin** if needed.
2. **Send invitation.** The person receives an email with a single-use link that expires after **48 hours**.
   No password is ever emailed or shown, not even to you.
3. They open the link, choose their own password and must set up two-step sign-in (authenticator app and
   backup codes) before they can see anything.
4. If the link expired or went to the wrong place: open the person → **Send a new invitation** (older links
   stop working) or **Revoke the invitation**.

**Change roles:** open the person → **Change roles and departments**. Give each person only what their work
needs. Removing a department takes effect at their next page.

**Other actions on a person's page**
* **Reset two-step sign-in (lost phone):** removes their authenticator and backup codes and signs them out;
  they set it up again at their next sign-in. Check it is really them first (phone call or in person).
* **Force password reset:** their password stops working immediately and they are signed out; they receive a
  single-use link to choose a new one.
* **Clear sign-in lockout:** after 5 wrong passwords an account is locked for an hour. Confirm it was really
  them before unlocking.
* **Deactivate:** for someone leaving or on long leave. They are signed out everywhere at once. **Reactivate**
  brings the account back.
* **Delete account:** permanent (they can never sign in again); the record is kept only so the audit history
  still makes sense.

**Safeguards you cannot switch off:** at most two active Super Admins; the last active Super Admin cannot be
demoted, deactivated or deleted; accounts unused for 60 days are flagged to you and switched off after 90 days
(Super Admins are flagged but never switched off automatically).

**Access review (every three months):** **Access review** lists every account with its departments, roles,
branch, two-step sign-in status and last sign-in. Remove roles people no longer need and deactivate accounts
of people who left. **Export CSV** is recorded in the audit log.

**Account audit trail:** every account and role change with who did it, when, from which IP address, and the
old and new values. If you ever see **"changed OUTSIDE the portal"** (you also get an email), someone changed
an account without using these screens, for example directly in the database. Treat it as a possible
break-in: follow `docs/INCIDENT_RESPONSE.md`, section 1.

**The very first Super Admin** is created by the technical lead on the server with
`manage.py create_super_admin` (it asks for the email, name and password). It refuses to run once a Super Admin
exists; every later account is invited from the portal.
