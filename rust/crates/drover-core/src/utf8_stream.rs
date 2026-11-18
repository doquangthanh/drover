//! Incremental UTF-8 decoding for PTY reads: a character split across two reads is kept until it completes,
//! invalid bytes become U+FFFD (same as Python's `codecs.getincrementaldecoder("utf-8")(errors="replace")`).

#[derive(Default)]
pub struct Utf8Stream {
    carry: Vec<u8>,
}

impl Utf8Stream {
    pub fn decode(&mut self, chunk: &[u8]) -> String {
        self.carry.extend_from_slice(chunk);
        let mut out = String::with_capacity(self.carry.len());
        let mut rest: &[u8] = &self.carry;
        loop {
            match std::str::from_utf8(rest) {
                Ok(s) => {
                    out.push_str(s);
                    rest = &[];
                    break;
                }
                Err(e) => {
                    let (valid, after) = rest.split_at(e.valid_up_to());
                    out.push_str(std::str::from_utf8(valid).unwrap_or_default());
                    match e.error_len() {
                        Some(n) => {
                            out.push('\u{FFFD}');
                            rest = &after[n..];
                        }
                        None => {
                            rest = after; // incomplete sequence at the end: wait for more bytes
                            break;
                        }
                    }
                }
            }
        }
        self.carry = rest.to_vec();
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_multibyte_char_is_joined() {
        let bytes = "ệ🎉".as_bytes();
        let mut d = Utf8Stream::default();
        let mut out = String::new();
        for b in bytes {
            out.push_str(&d.decode(&[*b]));
        }
        assert_eq!(out, "ệ🎉");
    }

    #[test]
    fn invalid_bytes_become_replacement_char() {
        let mut d = Utf8Stream::default();
        assert_eq!(d.decode(b"a\xffb"), "a\u{FFFD}b");
    }
}
