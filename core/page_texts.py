"""Default wording for every editable page heading and section, and for every editable form option list.

These are only DEFAULTS: on ``migrate`` a missing row is created from them (existing rows are never
overwritten), and templates fall back to them if a row is missing. Staff edit the real text in the admin
under "Page text" and "Form options".

To make a new page's wording editable: add a key here, use ``{% page_text "key" as pt %}`` in its template,
then run ``migrate`` (or ``manage.py sync_site_text``).
"""

from __future__ import annotations

from typing import TypedDict


class PageTextDefault(TypedDict, total=False):
    label: str
    eyebrow: str
    heading: str
    highlight: str
    intro: str


PAGE_TEXT_DEFAULTS: dict[str, PageTextDefault] = {
    # ---- home page
    "home_hero": {
        "label": "Home: hero (only shown when no hero slide is active)",
        "heading": "Rebuilding Lives.",
        "highlight": "Reviving Generations.",
    },
    "home_testimonies": {
        "label": "Home: testimonies slider",
        "eyebrow": "Lives rebuilt",
        "heading": "Testimonies",
    },
    "home_partners": {
        "label": "Home: partners logo strip",
        "eyebrow": "Building together",
        "heading": "Our partners",
    },
    "about_leadership": {
        "label": "About: leadership slider",
        "eyebrow": "Who leads us",
        "heading": "Our leadership",
    },
    "home_programmes": {
        "label": "Home: programmes section",
        "eyebrow": "What we do",
        "heading": "Our programmes",
    },
    "home_events": {
        "label": "Home: events section",
        "eyebrow": "Join us",
        "heading": "Upcoming events",
        "intro": "New events will be announced soon.",
    },
    "home_branches": {
        "label": "Home: branches section",
        "eyebrow": "Where we are",
        "heading": "Our branches",
    },
    "home_news": {"label": "Home: news section", "eyebrow": "Latest", "heading": "News & updates"},
    "home_card_prayer": {
        "label": "Home: prayer card",
        "heading": "Need prayer?",
        "intro": "Share your request in confidence. Our team will pray with you.",
    },
    "home_card_partner": {
        "label": "Home: partner card",
        "heading": "Partner with us",
        "intro": "Churches, organisations and individuals building together.",
    },
    "home_card_resources": {
        "label": "Home: sermons card",
        "heading": "Sermons & devotionals",
        "intro": "Teaching to help you grow, wherever you are.",
    },
    # ---- shared blocks
    "cta_band": {
        "label": "Every page: call-to-action band",
        "heading": "Be part of what God is rebuilding.",
        "intro": "Give, volunteer, or join us at an event. Every part matters.",
    },
    "footer_newsletter": {
        "label": "Every page: footer newsletter blurb",
        "heading": "Stay connected",
        "intro": "News, events and prayer points, about once a month.",
    },
    # ---- pages
    "about": {"label": "About page", "eyebrow": "About us", "heading": "Rebuilding lives through the Gospel"},
    "leadership": {
        "label": "Leadership page",
        "eyebrow": "Leadership",
        "heading": "The people serving the vision",
    },
    "programs": {
        "label": "Programmes page",
        "eyebrow": "Programmes",
        "heading": "How we rebuild lives",
        "intro": "Revival, discipleship, evangelism and leadership: each programme helps people grow in faith and serve.",
    },
    "branches": {"label": "Branches page", "eyebrow": "Branches", "heading": "Find a branch near you"},
    "events": {
        "label": "Events page",
        "eyebrow": "Events",
        "heading": "Gather. Worship. Grow.",
        "intro": "Conferences, outreaches and gatherings across our branches.",
    },
    "gallery": {
        "label": "Gallery page",
        "eyebrow": "Media",
        "heading": "Moments of revival",
        "intro": "Photos, videos, reports and testimonies from across the ministry.",
    },
    "videos": {"label": "Videos page", "eyebrow": "Media", "heading": "Videos"},
    "reports": {
        "label": "Reports page",
        "eyebrow": "Media",
        "heading": "Reports",
        "intro": "Ministry reports and publications.",
    },
    "testimonies": {
        "label": "Testimonies page",
        "eyebrow": "Testimonies",
        "heading": "Lives rebuilt",
        "intro": "Stories of what God is doing, shared with permission.",
    },
    "resources": {
        "label": "Sermons & resources page",
        "eyebrow": "Resources",
        "heading": "Sermons, devotionals & study materials",
    },
    "news": {"label": "News page", "eyebrow": "News", "heading": "News & announcements"},
    "get_involved": {
        "label": "Get involved (volunteer) page",
        "eyebrow": "Get involved",
        "heading": "Serve with us",
        "intro": "Use your gifts to help rebuild lives. Tell us a little about yourself and we will be in touch.",
    },
    "give": {
        "label": "Give page",
        "eyebrow": "Give",
        "heading": "Your generosity rebuilds lives",
        "intro": "Every gift supports revival conferences, evangelism, discipleship and the next generation of leaders.",
    },
    "partner": {
        "label": "Partner with us page",
        "eyebrow": "Partnership",
        "heading": "Partner with us",
        "intro": "Churches, organisations and individuals partnering in prayer, missions, resources and finance.",
    },
    "membership_register": {
        "label": "Membership registration page",
        "eyebrow": "Membership",
        "heading": "Become a member",
        "intro": "Thank you for your interest in becoming a member of Rebuilding Lives Ministry. Please complete "
        "the following information to help us understand you and your commitment to the ministry.",
    },
    "discipleship_register": {
        "label": "Discipleship registration page",
        "eyebrow": "Discipleship",
        "heading": "Grow as a disciple",
        "intro": "Our discipleship program is designed to help believers grow spiritually, understand God's Word, "
        "develop Christian character, and become effective servants of Christ.",
    },
    "finance_volunteer": {
        "label": "Finance & accountability volunteer page",
        "eyebrow": "Serve",
        "heading": "Finance & Accountability volunteers",
        "intro": "Rebuilding Lives Ministry welcomes responsible and trustworthy individuals with financial, "
        "accounting, bookkeeping, and administrative skills to serve in our Finance and Accountability Department.",
    },
    "pledge": {"label": "Give: pledge form page", "eyebrow": "Give", "heading": "Tell us about your gift"},
    "give_thanks": {"label": "Give: thank-you page", "heading": "Thank you for giving"},
    "prayer": {
        "label": "Prayer request page",
        "eyebrow": "Prayer",
        "heading": "How can we pray for you?",
        "intro": "Share your request in confidence. It is encrypted and read only by our prayer team. Name and contact details are optional.",
    },
    "contact": {"label": "Contact page", "eyebrow": "Contact", "heading": "We would love to hear from you"},
    "newsletter": {
        "label": "Newsletter sign-up page",
        "eyebrow": "Stay connected",
        "heading": "Get ministry updates",
        "intro": "News, events and prayer points by email. We will ask you to confirm, and you can unsubscribe at any time.",
    },
    "newsletter_unsubscribe": {
        "label": "Newsletter: unsubscribe page",
        "eyebrow": "Newsletter",
        "heading": "Unsubscribe",
    },
}


# (stored value, label shown to visitors). Values are stored in submissions, so they never change;
# labels can be renamed freely in the admin.
FORM_OPTION_DEFAULTS: dict[str, list[tuple[str, str]]] = {
    "volunteer_interest": [
        ("prayer", "Prayer & intercession"),
        ("worship", "Worship & music"),
        ("youth", "Youth ministry"),
        ("children", "Children's ministry"),
        ("evangelism", "Evangelism & outreach"),
        ("media", "Media & communications"),
        ("logistics", "Logistics & events"),
        ("teaching", "Teaching & discipleship"),
        ("admin", "Administration"),
        ("other", "Other"),
    ],
    "volunteer_availability": [
        ("weekdays", "Weekdays"),
        ("weekends", "Weekends"),
        ("evenings", "Evenings"),
        ("events", "Special events only"),
        ("flexible", "Flexible"),
    ],
    "contact_topic": [
        ("general", "General enquiry"),
        ("events", "Events"),
        ("partnership", "Partnership"),
        ("media", "Media & invitations"),
        ("other", "Other"),
    ],
    "partner_type": [
        ("individual", "Individual"),
        ("church", "Church"),
        ("ministry", "Ministry"),
        ("organisation", "Organisation"),
        ("institution", "Institution"),
    ],
    "partner_area": [
        ("evangelism", "Evangelism and outreach"),
        ("youth-revival", "Youth revival conferences"),
        ("discipleship", "Discipleship programs"),
        ("prayer", "Prayer and intercession"),
        ("financial", "Financial support"),
        ("missionary", "Missionary support"),
        ("resources", "Ministry resources and equipment"),
        ("leadership", "Leadership development"),
        ("other", "Other"),
    ],
    "partnership_type": [
        ("financial", "Financial"),
        ("prayer", "Prayer"),
        ("material", "Material support"),
        ("professional", "Professional/technical support"),
        ("collaboration", "Ministry collaboration"),
    ],
    "partner_interest": [
        ("financial", "Financial partnership"),
        ("prayer", "Prayer partnership"),
        ("missions", "Missions & outreach"),
        ("resources", "Equipment & resources"),
        ("other", "Other"),
    ],
}
