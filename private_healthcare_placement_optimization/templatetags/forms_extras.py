from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(value, css_class):
    """
    Adds a given CSS class to the field widget.
    """
    if hasattr(value, 'as_widget'):
        return value.as_widget(attrs={'class': css_class})
    return value


@register.filter
def split(value, delimiter=","):
    return value.split(delimiter)

@register.filter
def is_allowed_doc(doc_type):
    return doc_type in ['Resume', 'Extra Dose of Covid', 'Other Documents']
allowed_docs = [
    'Experience Document',
    # --- Medical Requirements ---
    'Medical Certificate Form',
    'X-Ray Result',
    'MMR Lab/Vax Record',
    'Varicella Lab/Vax Record',
    'TDAP Vax Record',
    'Hepatitis A Lab/Vax Record',
    'Hepatitis B Lab/Vax Record',
    # --- NACC Requirements ---
    'Covid Vaccination Certificate',
    'Vulnerable Sector Check',
    'CPR & First Aid',
    'Mask Fit Certificate',
    'Basic Life Support',
    'Flu Shot',
    # --- Other ---
    'Resume',
    'Extra Dose of Covid',
    'Other Documents',
    'Skills Passbook',
]

@register.filter
def is_document_status_section_allowed_doc(doc_type_display_name):
    return doc_type_display_name in allowed_docs

@register.filter
def document_group(doc_type_display_name):
    if doc_type_display_name in [
        'Experience Document',
    ]:
        return 'Experience'
    if doc_type_display_name in [
        'Medical Certificate Form',
        'X-Ray Result',
        'MMR Lab/Vax Record',
        'Varicella Lab/Vax Record',
        'TDAP Vax Record',
        'Hepatitis A Lab/Vax Record',  # ✅ new addition
        'Hepatitis B Lab/Vax Record',
    ]:
        return 'Medical Requirements'

    elif doc_type_display_name in [
        'Covid Vaccination Certificate',
        'Vulnerable Sector Check',
        'CPR & First Aid',
        'Mask Fit Certificate',
        'Basic Life Support',
        'Flu Shot',
    ]:
        return 'NACC Requirements'

    elif doc_type_display_name in [
        'Resume',
        'Extra Dose of Covid',
        'Other Documents',
    ]:
        return 'Additional Facility Requirements'

    elif doc_type_display_name == 'Skills Passbook':
        return 'Documents Required After Placement Completion'

    return ''


@register.filter
def get_item(dictionary, key):
    try:
        return dictionary.get(key)
    except Exception:
        return None

# Add last_item filter for safe access to the last element of a list
@register.filter
def last_item(value):
    try:
        return value[-1]
    except (IndexError, TypeError):
        return None



@register.filter(name='get_item')
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None  # fallback to avoid errors