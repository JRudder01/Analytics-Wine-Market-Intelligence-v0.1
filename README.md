# Wine Market Intelligence v0.3.15

Experimental selected-product-page catalog scan.

The catalog scan remains user-initiated and low-request. A catalog page is fetched once, likely same-site wine product links are discovered from that already-downloaded HTML, and individual product pages are fetched only after the administrator explicitly selects them.

This patch does not add browser automation, JavaScript execution, CAPTCHA/access-control bypass, automatic retries, or automatic database writes.
