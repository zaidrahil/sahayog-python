"""
translations.py
----------------
Minimal i18n for the "multilingual application" feature from the problem
statement. Two languages are wired up end-to-end as a demonstration
(English, Hindi); adding a third only means adding a new dict below - no
other code changes, since every template calls t('some_key') and never
hard-codes English text directly.
"""

TRANSLATIONS = {
    "en": {
        "app_name": "Sahayog",
        "tagline": "Cooperative-owned services, booked directly with verified workers",
        "hero_title": "Household help, owned by the people who do it",
        "hero_lede": "Sahayog connects verified electricians, plumbers, domestic help and more - all cooperative-federation members - directly with your household.",
        "login_tab": "Log in",
        "register_tab": "Register",
        "role_customer": "I need a service",
        "role_worker": "I provide a service",
        "field_name": "Full name",
        "field_phone": "Phone number",
        "field_password": "Password",
        "field_skills": "Your skills",
        "field_language": "Preferred language",
        "submit_login": "Log in",
        "submit_register": "Create account",
        "customer_dashboard": "My bookings",
        "book_new": "Book a new service",
        "field_category": "Type of service",
        "field_description": "Describe the problem",
        "field_urgent": "This is urgent",
        "submit_booking": "Find a worker",
        "worker_dashboard": "My jobs",
        "worker_available": "Available for new jobs",
        "worker_welfare_wallet": "Welfare wallet balance",
        "worker_rating": "Your rating",
        "admin_dashboard": "Federation dashboard",
        "admin_pending_workers": "Workers awaiting verification",
        "admin_forecast": "Demand forecast",
        "verify_action": "Verify worker",
        "no_bookings": "No bookings yet.",
        "no_pending_workers": "All workers are verified.",
        "logout": "Log out",
        "settings": "Settings",
    },
    "hi": {
        "app_name": "सहयोग",
        "tagline": "सहकारी स्वामित्व वाली सेवाएँ, सत्यापित कामगारों के साथ सीधे बुक करें",
        "hero_title": "घरेलू सहायता, जिसे करने वाले लोग ही चलाते हैं",
        "hero_lede": "सहयोग सत्यापित इलेक्ट्रीशियन, प्लंबर, घरेलू सहायक आदि को सीधे आपके घर से जोड़ता है।",
        "login_tab": "लॉग इन करें",
        "register_tab": "पंजीकरण करें",
        "role_customer": "मुझे सेवा चाहिए",
        "role_worker": "मैं सेवा प्रदान करता/करती हूँ",
        "field_name": "पूरा नाम",
        "field_phone": "फ़ोन नंबर",
        "field_password": "पासवर्ड",
        "field_skills": "आपके कौशल",
        "field_language": "पसंदीदा भाषा",
        "submit_login": "लॉग इन करें",
        "submit_register": "खाता बनाएँ",
        "customer_dashboard": "मेरी बुकिंग",
        "book_new": "नई सेवा बुक करें",
        "field_category": "सेवा का प्रकार",
        "field_description": "समस्या का विवरण दें",
        "field_urgent": "यह जरूरी है",
        "submit_booking": "कामगार खोजें",
        "worker_dashboard": "मेरे काम",
        "worker_available": "नए काम के लिए उपलब्ध",
        "worker_welfare_wallet": "कल्याण वॉलेट शेष",
        "worker_rating": "आपकी रेटिंग",
        "admin_dashboard": "फेडरेशन डैशबोर्ड",
        "admin_pending_workers": "सत्यापन की प्रतीक्षा कर रहे कामगार",
        "admin_forecast": "मांग का पूर्वानुमान",
        "verify_action": "कामगार सत्यापित करें",
        "no_bookings": "अभी तक कोई बुकिंग नहीं।",
        "no_pending_workers": "सभी कामगार सत्यापित हैं।",
        "logout": "लॉग आउट",
        "settings": "सेटिंग्स",
    },
}


def translate(key, lang):
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
