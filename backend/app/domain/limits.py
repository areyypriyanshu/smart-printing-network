"""The limits of the product, in one place.

The price of an order is pages x copies x rate, and the price is held
in a column that is a 32 bit integer. These are the numbers that keep
the largest order the platform takes inside that column, and they are
here, in the pure layer, because they are rules about what the product
will accept rather than about how it is deployed.

The multiplication below is the rule: the biggest price that can be
asked for has to be smaller than the biggest price that can be held,
and if a deployment raises the page limit past it, the application
refuses to start rather than discovering it on a customer's order.
"""

#: The most pages a file may have. It is the upload limit, and it is
#: also the largest number of pages an order can be for.
MAX_PAGES = 300

#: The most copies of a file one order can be for.
MAX_COPIES = 100

#: The most a page can cost, in paise. Fifty thousand paise is five
#: hundred rupees, which is more than a print shop asks for a page.
MAX_RATE_PAISE = 50_000

#: The most a shop can ask for as its minimum order, in paise. It is
#: the price of the whole order and not of a page, so the ceiling is
#: larger, but the same column holds it and the same rule applies.
MAX_MIN_ORDER_PAISE = 10_000_000

#: The largest price the column that holds an order's price can hold.
MAX_PRICE_PAISE = 2_147_483_647

#: The largest price the platform can be asked for, in paise.
MAX_ORDER_PRICE_PAISE = MAX_PAGES * MAX_COPIES * MAX_RATE_PAISE
