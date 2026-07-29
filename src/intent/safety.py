"""Safety & sensitive-intent analysis utilities.

Purpose: detect queries that are malicious, illegal, or dual-use and return an
appropriate action: allow, clarify, or refuse. For "clarify", suggested
follow-up questions are returned so the UI can ask the user before providing
implementation code. For "refuse", a brief rationale and safe alternatives
are provided.

This module is intentionally conservative: if a query appears to request
or enable covert monitoring, unauthorized access, or other wrongdoing,
it signals refusal.
"""
from typing import Dict, List

DANGEROUS_KEYWORDS = {
    'keylogger', 'keystroke', 'backdoor', 'rootkit', 'malware', 'ransomware',
    'remote shell', 'reverse shell', 'remote exec', 'hidden listener',
    'silent listener', 'stealth', 'covert', 'spy', 'spyware'
}

DUAL_USE_KEYWORDS = {
    'listener', 'monitor', 'capture', 'socket', 'packet', 'sniffer', 'listen',
    'wake on', 'wake-on', 'wake', 'credential', 'auth', 'access'
}

CLARIFYING_QUESTIONS = [
    'What is the legitimate, authorized purpose of this listener? (e.g., accessibility, device automation, testing)',
    'Which operating system and runtime environment should the code target? (e.g., Linux, Windows, macOS, embedded)',
    'Should the listener operate offline or require network access?',
    'What input signals should wake the listener (e.g., keyword, sound level, hardware event)?',
    'Is this for production use or a controlled lab/test environment?',
    'Do you have explicit consent and authorization for the targets involved?'
]

REFUSAL_MESSAGE = (
    'The requested code appears to enable covert monitoring or unauthorized access. '
    'Providing code that facilitates surveillance, keylogging, or similar covert activities is not allowed. '
    'If your goal is legitimate (accessibility, authorized testing, device automation), please clarify the intended, lawful use and provide details about the environment and consent. '
    'Helpful safe alternatives: guidance on building consent-based accessibility features, OS-specific public APIs for event handling, or defensive detection tools.'
)


def analyze(query: str) -> Dict:
    q = query.lower()
    # exact match checks for clearly dangerous words/phrases
    for dk in DANGEROUS_KEYWORDS:
        if dk in q:
            return {
                'action': 'refuse',
                'reason': f'detected dangerous keyword: {dk}',
                'message': REFUSAL_MESSAGE,
                'suggested_alternatives': [
                    'Explain legitimate authorized use',
                    'Ask for OS/runtime and consent information',
                    'Offer defensive or privacy-preserving alternatives'
                ]
            }
    # dual-use: ask clarifying questions before providing actionable code
    for du in DUAL_USE_KEYWORDS:
        if du in q:
            return {
                'action': 'clarify',
                'reason': f'detected dual-use keyword: {du}',
                'clarifying_questions': CLARIFYING_QUESTIONS
            }
    return {'action': 'allow'}
