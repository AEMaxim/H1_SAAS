import datetime as dt
import json
import re

import requests
from flask import Flask, jsonify, request, render_template

API_TOKEN = "###"
WEATHER_API_KEY = "###"
BASE_WEATHER_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"

app = Flask(__name__)


class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv["message"] = self.message
        return rv


class WeatherService:
    def fetch_weather(self, location, date):

        try:
            parsed_date = dt.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise InvalidUsage("Invalid date format, expected YYYY-MM-DD", status_code=400)

        if parsed_date < dt.date.today():
            raise InvalidUsage("Error fetching weather data: cannot request past dates", status_code=400)

        weather_url = (
            f"{BASE_WEATHER_URL}/{location}/{date}"
            f"?key={WEATHER_API_KEY}&unitGroup=metric&elements=datetime%2Caddress%2Ctemp%2Cfeelslike%2Chumidity%2Cprecipprob%2Cpreciptype%2Cwindspeedmean%2Cpressure%2Ccloudcover%2Cvisibility%2Cuvindex&include=fcst%2Cdays&options=nonulls&contentType=json"
        )

        response = requests.get(weather_url)
        if response.status_code != 200:
            raise InvalidUsage("Error fetching weather data", status_code=response.status_code)

        return response.json()

    def generate_recommendation(self, weather_data):
        try:
            sports_recommendation = self._get_sports_recommendation(weather_data)

        except Exception as e:
            sports_recommendation = {"error": f"Error generating sports recommendation: {e}"}

        return sports_recommendation

    def _get_sports_recommendation(self, weather_data):
        data_parsed = weather_data["days"][0]

        output = f"""
            Based on the weather data on {data_parsed['datetime']}, recommend suitable outdoor activities and provide relevant health advice. The current conditions are:

            Temperature: {data_parsed['temp']}°C (Feels like: {data_parsed['feelslike']}°C)
            Precipitation probability: {data_parsed['precipprob']}%
            Wind speed: {data_parsed['windspeedmean']} km/h
            Humidity: {data_parsed['humidity']}%
            Cloud cover: {data_parsed['cloudcover']}%
            Visibility: {data_parsed['visibility']} km
            UV index: {data_parsed['uvindex']}
            Pressure: {data_parsed['pressure']} mb

            Provide a brief recommendation for:
                1. Whether conditions are suitable for running, walking, or other outdoor activities
                2. Any specific activities particularly well-suited to today's weather
                3. Important health or safety precautions (such as UV protection, hydration needs, or visibility concerns)
            Keep your response informal, concise and friendly, focusing on practical advice for today's conditions. 
            Answer meaningfully but briefly. Make sure that your description for each category does not exceed 220 characters!
            """

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": "Bearer ###",
            "Content-Type": "application/json"
        }

        data = {
            "model": "deepseek/deepseek-chat:free",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Please respond only in valid JSON format with the following structure: "
                        "{\"sports_recommendation\": {"
                        "\"activity_recommendation\": \"<string>\", "
                        "\"health_safety\": \"<string>\""
                        "}}"
                    )
                },
                {"role": "user", "content": output}
            ]
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")

        try:
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            content = re.sub(r'^```json\n|\n```$', '', content.strip())

            if not content:
                raise Exception("No content found in API response")
        except (json.JSONDecodeError, KeyError) as e:
            raise Exception(f"Error parsing API response: {e} | Raw response: {response.text}")

        return json.loads(content)


weather_service = WeatherService()


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@app.route("/")
def home_page():
    return render_template('index.html')


@app.route("/content/api/v1/weather", methods=["POST"])
def weather_endpoint():
    json_data = request.get_json()

    for param in ("token", "location", "date", "requester_name"):
        if not json_data.get(param):
            raise InvalidUsage(f"{param} is required", status_code=400)

    if json_data.get("token") != API_TOKEN:
        raise InvalidUsage("wrong API token", status_code=403)

    location = json_data.get("location")
    date = json_data.get("date")
    requester_name = json_data.get("requester_name")
    utc_timestamp = dt.datetime.utcnow().isoformat() + "Z"

    weather_data = weather_service.fetch_weather(location, date)
    recommendation = weather_service.generate_recommendation(weather_data)

    result = {
        "requester_name": requester_name,
        "timestamp": utc_timestamp,
        "location": location,
        "date": date,
        "weather": weather_data,
        "sports_recommendation": recommendation
    }

    return result

