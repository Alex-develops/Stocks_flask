import os


from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)



# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    user_id = session["user_id"]
    user = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id,)
    cash = user[0]["cash"]

    rows = db.execute("SELECT symbol, name, sum(shares) as shares, price, sum(price*shares) as total_cost, sum(total_cost) as total_cost_sum FROM stocks WHERE user_id=:user_id GROUP BY symbol HAVING sum(shares) > 0", user_id=user_id)
    total_cost_sum = 0

    for row in rows:

        name = row["name"]
        symbol = row["symbol"]
        shares = int(row["shares"])
        quoted_stock = lookup(symbol)
        price = float(quoted_stock["price"])
        total_cost = float(shares*price)
        total_cost_sum += total_cost


    grand_total = total_cost_sum+cash
    return render_template("index.html", cash = cash, rows = rows, grand_total = grand_total)


@app.route("/buy", methods = ["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""


    if request.method =="POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        shares = int(request.form.get("shares"))
        price = stock.get("price")
        total_cost = shares*stock["price"]
        name = stock.get("name")
        transaction_type = "purchase"
        #Validations
        if not symbol:
            return apology("Choose a stock to buy!")

        if stock is None:
            return apology ("Enter a valid symbol", 403)
        if not shares or shares < 1:
            return apology("Enter a valid number of shares to buy!")
        #validating that the current user is the one who bought the shares and who sees the portfolio
        user_id = session["user_id"]

        user = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)

        balance = user[0]["cash"]-total_cost

        if total_cost > balance:
            return apology("Not enough funds")
        else:
            db.execute ("UPDATE users SET cash=:balance WHERE id=:id", balance = balance, id = user_id)
            db.execute("INSERT INTO stocks(user_id, symbol, name, shares, price, total_cost, transaction_type ) VALUES(:user_id, :symbol, :name, :shares, :price, :total_cost, :transaction_type)", user_id=user_id, name=name, symbol=symbol, shares=shares, price=price, total_cost=total_cost, transaction_type=transaction_type)

        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    user_id=session["user_id"]

    rows = db.execute("SELECT symbol, shares, price, lastmodified, transaction_type FROM stocks WHERE user_id=:user_id ORDER BY lastmodified ASC", user_id=user_id)


    return render_template("history.html", rows = rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Enter a symbol")
        stock = lookup(symbol)

        if stock is None:
            return apology ("Enter a valid symbol")
        else:
            return render_template("quoted.html", stock=stock )




@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

         # Ensure username was provided

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        hash=generate_password_hash(password)

        if not username:
            return apology("must provide username", 400)

        # Ensure password was provided
        if not password:
            return apology("must provide password", 400)


        #Ensure password confirmation is provided
        if not confirmation:
            return apology("must confirm password", 400)
        #Check if password matches
        if password!= confirmation:
            return apology("password does not match", 400)
        #query db for username:

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        #check if username is available

        if len(rows)!= 0:
            return apology("username already exists", 400)
        else:
            # hash the password with generate_password_hash
            #insert username and hash in DB
            db.execute("INSERT INTO users(username, hash) VALUES(:username, :hash)", username=username, hash=hash)

            #go back to homepage
            return redirect("/")

    else:
        return render_template("register.html")






@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    """Sell shares of stock"""
    #Access the current user
    user_id= session["user_id"]

    if request.method =="POST":
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("Enter a symbol or number of shares", 400)



        #Define data
        symbol=request.form.get("symbol")
        shares=int(request.form.get("shares"))
        stock=lookup(symbol)
        price=stock.get("price")
        total_cost=int(shares)*stock["price"]
        name=stock.get("name")
        transaction_type="sale"

        if shares < 1:
            return apology("Enter a valid number of shares")

        if stock is None:
            return apology("Enter a valid symbol")

        #Access existing data in DB

        rows= db.execute("SELECT symbol, sum(shares) as shares FROM stocks WHERE user_id=:user_id GROUP BY symbol", user_id=user_id)


        #Validate if the current user owns the shares they are trying to sell
        for row in rows:
            if row["symbol"]==symbol:
                if shares > row["shares"]:
                    return apology("Enter a valid number of shares", 400)



        user=db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
        new_cash=user[0]["cash"]+total_cost
        #Add transaction to the db
        #Update DB cash of the user

        db.execute ("UPDATE users SET cash=:new_cash WHERE id=:id", new_cash=new_cash, id=user_id)
        db.execute("INSERT INTO stocks (user_id, symbol, name, shares, price, total_cost, transaction_type) VALUES(:user_id, :symbol, :name, :shares, :price, :total_cost, :transaction_type)", user_id=user_id, name=name, symbol=symbol, shares= -1*shares, price=price, total_cost=total_cost, transaction_type=transaction_type)

        return redirect("/")

    else:
        share_symbols=[]
        symbs = db.execute("SELECT symbol FROM stocks WHERE user_id=:user_id GROUP BY symbol",
        user_id=user_id)
        for symb in symbs:
            share_symbols.append(symb)
        return render_template("sell.html", share_symbols=share_symbols)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
    for code in default_exceptions:
        app.errorhandler(code)(errorhandler)
