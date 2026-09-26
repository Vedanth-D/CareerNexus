import sys
import os
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.input_validation import (
    sanitize_text,
    validate_and_sanitize_email,
    validate_password,
    validate_token,
    validate_job_id,
    validate_search_query,
    validate_uploaded_file,
    validate_json_field
)
from server import app

client = TestClient(app)

def test_email_validation():
    print('\n--- 1. Testing Email Validation ---')
    assert validate_and_sanitize_email('  TEST@Example.com  ') == 'test@example.com'
    assert validate_and_sanitize_email('user.name+tag@sub.domain.org') == 'user.name+tag@sub.domain.org'
    print('  [PASS] Valid emails sanitized and accepted.')
    
    invalid_emails = [
        'plainaddress',
        '@missinguser.com',
        'user@.com',
        'user@domain..com',
        'user name@domain.com',
        'a' * 250 + '@domain.com'
    ]
    for bad in invalid_emails:
        try:
            validate_and_sanitize_email(bad)
            assert False, f'Failed to reject invalid email: {bad}'
        except HTTPException as e:
            assert e.status_code == 400
    print('  [PASS] All invalid/oversized emails rejected with HTTP 400.')

def test_password_validation():
    print('\n--- 2. Testing Password Validation ---')
    assert validate_password('ValidPassword123!') == 'ValidPassword123!'
    print('  [PASS] Valid password accepted.')
    
    try:
        validate_password('short')
        assert False, 'Failed to reject short password'
    except HTTPException:
        pass
        
    try:
        validate_password('A' * 129)
        assert False, 'Failed to reject oversized password'
    except HTTPException:
        pass
        
    try:
        validate_password('pass\x00word')
        assert False, 'Failed to reject null byte in password'
    except HTTPException:
        pass
    print('  [PASS] Short, oversized (Hash-DoS), and null-byte passwords rejected.')

def test_script_injection_xss_sanitization():
    print('\n--- 3. Testing XSS / Script Injection Prevention ---')
    xss_payloads = [
        ('<script>alert("XSS")</script>Hello', 'Hello'),
        ('javascript:alert(1)Click Me', 'Click Me'),
        ('<iframe src="evil.com"></iframe>Content', 'Content'),
        ('<img src="x" onerror="alert(1)">Text', '<img src="x" >Text'),
        ('Null\x00Byte', 'NullByte')
    ]
    for raw, expected in xss_payloads:
        cleaned = sanitize_text(raw)
        assert '<script>' not in cleaned
        assert 'javascript:' not in cleaned
        assert 'onerror=' not in cleaned
        assert '\x00' not in cleaned
    print('  [PASS] Dangerous XSS, script tags, inline handlers, and null bytes neutralized.')

def test_command_injection_sanitization():
    print('\n--- 4. Testing Command Injection Prevention ---')
    cmd_payloads = [
        'Software Engineer; cat /etc/passwd',
        'Developer | rm -rf /',
        'Manager && whoami',
        'Architect `id`',
        'Engineer > /dev/null'
    ]
    for payload in cmd_payloads:
        cleaned = validate_search_query(payload)
        for bad_char in [';', '|', '&', '`', '>', '<']:
            assert bad_char not in cleaned
    print('  [PASS] Shell metacharacters stripped from input parameters.')

def test_unsafe_file_upload_controls():
    print('\n--- 5. Testing Unsafe File Upload Security ---')
    class DummyUploadFile:
        def __init__(self, filename):
            self.filename = filename

    try:
        validate_uploaded_file(DummyUploadFile('../../../script.php'), b'<?php echo 1; ?>')
        assert False, 'Failed to block PHP executable upload'
    except HTTPException as e:
        assert e.status_code == 400
    print('  [PASS] Blocked dangerous executable extension (.php).')

    try:
        validate_uploaded_file(DummyUploadFile('resume.pdf'), b'This is fake pdf content')
        assert False, 'Failed to detect invalid PDF magic header'
    except HTTPException as e:
        assert e.status_code == 400
    print('  [PASS] Detected spoofed PDF with missing %PDF- header.')

    filename, ext = validate_uploaded_file(DummyUploadFile('MyResume.pdf'), b'%PDF-1.4 header content')
    assert filename == 'MyResume.pdf'
    assert ext == '.pdf'
    print('  [PASS] Valid PDF with authentic header accepted.')

    try:
        validate_uploaded_file(DummyUploadFile('large.txt'), b'A' * (6 * 1024 * 1024))
        assert False, 'Failed to reject >5MB file'
    except HTTPException as e:
        assert e.status_code == 413
    print('  [PASS] Oversized 6MB file rejected with HTTP 413 Payload Too Large.')

def test_token_and_job_id_validation():
    print('\n--- 6. Testing Token and Job ID Validation ---')
    assert validate_token('a1b2c3d4e5f67890a1b2c3d4e5f67890') == 'a1b2c3d4e5f67890a1b2c3d4e5f67890'
    
    try:
        validate_token('{"$gt": ""}')
        assert False, 'Failed to reject invalid token'
    except HTTPException:
        pass
    print('  [PASS] Valid tokens accepted, injection payloads rejected.')

    assert validate_job_id('remotive_12345') == 'remotive_12345'
    
    try:
        validate_job_id('../../../etc/passwd')
        assert False, 'Failed to block path traversal in job_id'
    except HTTPException:
        pass
    print('  [PASS] Path traversal in job_id rejected.')

def test_http_endpoint_validation():
    print('\n--- 7. Testing HTTP Endpoints with Malicious Payloads ---')
    resp = client.post('/register', data={'email': 'invalid-email', 'password': 'Password123!'})
    assert resp.status_code == 400
    assert 'Invalid email format' in resp.json()['detail']
    print('  [PASS] POST /register rejected invalid email format.')

    files = {'file': ('shell.py', b'print(1)', 'text/x-python')}
    resp = client.post('/upload-resume', files=files, cookies={'session_id': 'dummy'})
    assert resp.status_code in (400, 401)
    print('  [PASS] POST /upload-resume rejected unauthorized/executable file upload.')

def run_all_tests():
    print('==================================================')
    print('   RUNNING INPUT VALIDATION & SECURITY SUITE      ')
    print('==================================================')
    test_email_validation()
    test_password_validation()
    test_script_injection_xss_sanitization()
    test_command_injection_sanitization()
    test_unsafe_file_upload_controls()
    test_token_and_job_id_validation()
    test_http_endpoint_validation()
    print('\n[SUCCESS] ALL INPUT VALIDATION & SECURITY TESTS PASSED!')
    print('==================================================')

if __name__ == '__main__':
    run_all_tests()