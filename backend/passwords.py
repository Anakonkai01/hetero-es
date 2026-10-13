"""Password rules for people who register themselves.

Eight characters are enough because guessing is slowed down elsewhere (sign-in throttling, memory-hard hashing); what
matters more is refusing the passwords that are tried first. No composition rules: they make passwords harder to type
and easier to guess.
"""
MIN_LENGTH = 8
_COMMON = frozenset({
    'password', 'password1', 'password12', 'password123', 'password1234', 'passw0rd', 'p@ssw0rd', 'p@ssword',
    '12345678', '123456789', '1234567890', '12341234', '87654321', '11111111', '00000000', '11223344', '123123123',
    'qwertyui', 'qwertyuiop', 'qwerty12', 'qwerty123', 'qwerty1234', 'asdfghjk', 'asdfghjkl', 'zxcvbnm1', '1q2w3e4r', '1qaz2wsx',
    'abcd1234', 'abc12345', 'abcdefgh', 'iloveyou', 'letmein1', 'welcome1', 'admin123', 'administrator', 'changeme', 'trustno1',
    'heteroes', 'heteroes1', 'heteroes123', 'hetero-es',
})


def password_problem(password: str, username: str = '', display_name: str = '') -> str | None:
    """Return a sentence for the person registering, or None when the password is acceptable."""
    if len(password) < MIN_LENGTH:
        return f'Use at least {MIN_LENGTH} characters.'
    folded = password.casefold().strip()
    if not folded or folded in _COMMON or len(set(folded)) == 1:
        return 'This password is too easy to guess. Choose another one.'
    if any(name and folded == name.casefold().strip() for name in (username, display_name)):
        return 'The password must not be your username or display name.'
    return None
