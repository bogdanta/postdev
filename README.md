
# #postdev
Postboard service written in Django/Python.
This is a stripped down/mockup version of the #post application found on the ONEm platform.
It uses the ONEm developer framework.


## Direct usage
Head to https://poc.onem.zone/ and send #postdev.

## Installation

Clone the repo:
```
git clone https://github.com/bogdanta/postdev.git
```

Go to the repo's root folder:
```
cd postdev
```

Install the requirements(in a virtual environment):
```
pip install -r requirements.txt
```

Migrate the models and start the a local server:
```
python manage.py migrate
python manage.py runserver
```

Install [ngrok](https://ngrok.com/download) and start a tunnel:
```
ngrok http 8000
```
Register the app on the [ONEm developer portal](https://developer-portal-poc.onem.zone/))(under a different name eg. #postnew):
Set the callback URL to the forwarding address obtained from ngrok's output, go to the [sandbox](https://poc.onem.zone/) and send #postnew.


If the app is deployed to Heroku the callback URL will be: https://AppName.herokuapp.com

### Deploy to Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)
