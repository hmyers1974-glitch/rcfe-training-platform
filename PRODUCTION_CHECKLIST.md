# Production / Compliance Checklist

## Before public launch
- [ ] Change all seeded passwords.
- [ ] Set a long random `SECRET_KEY`.
- [ ] Use HTTPS only.
- [ ] Move from SQLite to a managed relational database if expecting concurrent users.
- [ ] Add CSRF protection.
- [ ] Add brute-force/login rate limiting.
- [ ] Add password reset and email verification.
- [ ] Add privacy policy and consent language.
- [ ] Add accessibility review (keyboard navigation, contrast, labels, screen reader flow).
- [ ] Configure backups and test restoration.
- [ ] Define three-year record-retention workflow consistent with vendor policy.
- [ ] Freeze course version before ACB review.
- [ ] Create ACB reviewer account and verify read-only access.
- [ ] Verify every self-paced module has the required interaction + feedback.
- [ ] Verify time-on-task logic with the final approved course design.
- [ ] Confirm current ACB submission requirements before filing.
