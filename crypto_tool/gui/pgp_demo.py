"""PGP Demo — simple Tkinter UI to generate RSA keys, encrypt and decrypt text.

Run as a module: `python -m crypto_tool.gui.pgp_demo`
"""

from __future__ import annotations

import base64
import tkinter as tk
from tkinter import messagebox

from Crypto.PublicKey import RSA

from crypto_tool.core import pgp


def _make_text(parent, height=8):
    txt = tk.Text(parent, height=height, wrap=tk.WORD)
    txt.pack(fill=tk.BOTH, expand=True)
    return txt


class PGPDemo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PGP Demo — simple RSA hybrid encrypt/decrypt")
        self.geometry("900x600")

        top = tk.Frame(self)
        top.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = tk.Frame(top)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right = tk.Frame(top)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Plaintext
        tk.Label(left, text="Plaintext:").pack(anchor=tk.W)
        self.plain_txt = _make_text(left, height=10)

        # Recipient public key
        tk.Label(left, text="Recipient public key (PEM):").pack(anchor=tk.W, pady=(6, 0))
        self.pub_txt = _make_text(left, height=6)

        btn_row = tk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        tk.Button(btn_row, text="Generate Keypair", command=self._gen_keys).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Encrypt → Ciphertext", command=self._encrypt).pack(side=tk.LEFT, padx=6)

        # Ciphertext output
        tk.Label(right, text="Ciphertext (base64):").pack(anchor=tk.W)
        self.ct_txt = _make_text(right, height=10)

        tk.Label(right, text="Recipient private key (PEM) for decryption:").pack(anchor=tk.W, pady=(6, 0))
        self.priv_txt = _make_text(right, height=6)

        bot_row = tk.Frame(right)
        bot_row.pack(fill=tk.X, pady=(6, 0))
        tk.Button(bot_row, text="Decrypt → Plaintext", command=self._decrypt).pack(side=tk.LEFT)
        tk.Button(bot_row, text="Clear All", command=self._clear_all).pack(side=tk.LEFT, padx=6)

        self.status = tk.Label(self, text="Ready", anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _set_status(self, msg: str):
        self.status.config(text=msg)

    def _gen_keys(self):
        priv, pub = pgp.generate_rsa_keypair(2048)
        self.priv_txt.delete("1.0", tk.END)
        self.priv_txt.insert("1.0", priv.decode("utf-8"))
        self.pub_txt.delete("1.0", tk.END)
        self.pub_txt.insert("1.0", pub.decode("utf-8"))
        self._set_status("Generated RSA keypair")

    def _encrypt(self):
        pub_pem = self.pub_txt.get("1.0", tk.END).strip().encode("utf-8")
        plain = self.plain_txt.get("1.0", tk.END).encode("utf-8")
        if not pub_pem or not plain.strip():
            messagebox.showwarning("Missing", "Please provide plaintext and recipient public key.")
            return
        try:
            envelope = pgp.encrypt(pub_pem, plain)
            self.ct_txt.delete("1.0", tk.END)
            self.ct_txt.insert("1.0", base64.b64encode(envelope).decode("ascii"))
            self._set_status("Encrypted (base64 shown)")
        except Exception as exc:
            messagebox.showerror("Encrypt error", str(exc))
            self._set_status(f"Error: {exc}")

    def _decrypt(self):
        priv_pem = self.priv_txt.get("1.0", tk.END).strip().encode("utf-8")
        ct_b64 = self.ct_txt.get("1.0", tk.END).strip()
        if not priv_pem or not ct_b64:
            messagebox.showwarning("Missing", "Please provide ciphertext and private key.")
            return
        try:
            envelope = base64.b64decode(ct_b64)
            pt = pgp.decrypt(priv_pem, envelope)
            self.plain_txt.delete("1.0", tk.END)
            try:
                self.plain_txt.insert("1.0", pt.decode("utf-8"))
            except Exception:
                # binary fallback
                self.plain_txt.insert("1.0", repr(pt))
            self._set_status("Decryption successful")
        except Exception as exc:
            messagebox.showerror("Decrypt error", str(exc))
            self._set_status(f"Error: {exc}")

    def _clear_all(self):
        for w in (self.plain_txt, self.pub_txt, self.priv_txt, self.ct_txt):
            w.delete("1.0", tk.END)
        self._set_status("Cleared")


def main():
    app = PGPDemo()
    app.mainloop()


if __name__ == "__main__":
    main()
