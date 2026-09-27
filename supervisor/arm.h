/* arm.h — is the owner's token present? one answer, shared by bench and bench-helper. */
#ifndef ARM_H
#define ARM_H

#define TOKEN_REL "sessions/OWNER_TOKEN"

/* 1 iff env_token names an existing regular file, or <root>/sessions/OWNER_TOKEN is one.
   presence only; the content is not read. env_token may be NULL or empty. */
int owner_token_present(const char *root, const char *env_token);

#endif
