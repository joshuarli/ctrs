extern crate proc_macro;

use proc_macro::{Literal, TokenStream, TokenTree};

/// `shout!()` expands to the literal "fixture target ok". It compiles for
/// the build host and runs there during expansion — the host check the
/// fixture exists to prove.
#[proc_macro]
pub fn shout(_input: TokenStream) -> TokenStream {
    TokenStream::from(TokenTree::from(Literal::string("fixture target ok")))
}
