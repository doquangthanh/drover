//! Parse OSC 7501 ("Program Status Protocol") self-reports from raw terminal output.
//!
//! Format: `ESC ] 7501 ; key=value[:key=value...] (BEL | ESC \)`, e.g. `ESC]7501;state=blocked:app=my-agent BEL`.
//! Port of `drover/status/osc7501_parser.py`.

use std::collections::BTreeMap;
use std::sync::LazyLock;

use regex::Regex;

static OSC_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\x1b\]7501;([^\x07\x1b]*)(?:\x07|\x1b\\)").expect("valid regex"));
const ALLOWED: [&str; 4] = ["working", "blocked", "idle", "done"];

/// The last valid report in `chunk` (fields by key), or None.
pub fn parse_osc7501(chunk: &str) -> Option<BTreeMap<String, String>> {
    let mut last = None;
    for caps in OSC_RE.captures_iter(chunk) {
        let mut fields = BTreeMap::new();
        for part in caps[1].split(':') {
            let (key, value) = part.split_once('=').unwrap_or((part, ""));
            if !key.is_empty() {
                fields.insert(key.trim().to_string(), value.trim().to_string());
            }
        }
        if fields.get("state").is_some_and(|s| ALLOWED.contains(&s.as_str())) {
            last = Some(fields);
        }
    }
    last
}

#[cfg(test)]
mod tests {
    use super::*;

    const ESC: &str = "\x1b";
    const BEL: &str = "\x07";

    fn map(pairs: &[(&str, &str)]) -> Option<BTreeMap<String, String>> {
        Some(pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect())
    }

    #[test]
    fn bel_terminated_report_with_extra_field() {
        let got = parse_osc7501(&format!("{ESC}]7501;state=blocked:app=my-agent{BEL}"));
        assert_eq!(got, map(&[("state", "blocked"), ("app", "my-agent")]));
    }

    #[test]
    fn st_terminated_report_is_parsed() {
        assert_eq!(parse_osc7501(&format!("output\r\n{ESC}]7501;state=done{ESC}\\more")), map(&[("state", "done")]));
    }

    #[test]
    fn report_embedded_in_normal_output_is_found() {
        let chunk = format!("build ok\r\n{ESC}]7501;state=idle{BEL}prompt> ");
        assert_eq!(parse_osc7501(&chunk), map(&[("state", "idle")]));
    }

    #[test]
    fn last_valid_report_in_chunk_wins() {
        let chunk = format!("{ESC}]7501;state=working{BEL}...{ESC}]7501;state=idle{BEL}");
        assert_eq!(parse_osc7501(&chunk).unwrap()["state"], "idle");
    }

    #[test]
    fn invalid_state_after_valid_one_is_ignored() {
        let chunk = format!("{ESC}]7501;state=blocked{BEL}{ESC}]7501;state=exploding{BEL}");
        assert_eq!(parse_osc7501(&chunk), map(&[("state", "blocked")]));
    }

    #[test]
    fn whitespace_around_key_and_value_is_stripped() {
        assert_eq!(parse_osc7501(&format!("{ESC}]7501; state = working {BEL}")), map(&[("state", "working")]));
    }

    #[test]
    fn invalid_or_missing_reports_return_none() {
        for chunk in [
            String::new(),
            "plain text only".into(),
            format!("{ESC}]7501;state=bogus{BEL}"),
            format!("{ESC}]7501;app=x{BEL}"),
            format!("{ESC}]7501;state={BEL}"),
            format!("{ESC}]7501;state=idle"),
            format!("{ESC}]7502;state=idle{BEL}"),
        ] {
            assert_eq!(parse_osc7501(&chunk), None, "{chunk:?}");
        }
    }
}
