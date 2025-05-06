from BOT_TOKEN import BOT_TOKEN
from Weather_API_TOKEN import WEATHER_API_KEY

from telegram.ext import Application, MessageHandler, CommandHandler, filters
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

import time, sqlite3, requests, aiohttp
import httpx, datetime, re

user_state = {}

GREETINGS = ["привет", "здарова", "здравствуй", "hi", "hello"]
GOODBYES = ["пока", "до свидания", "бай", "до встречи", "пака"]

CUSTOM_RESPONSES = {
    "как дела": "Всё отлично, спасибо!",
    "что ты умеешь": "Я могу приветствовать, считать, искать информацию о городе.",
    "спасибо": "Пожалуйста!",
    "ты классный": "Благодарю 😊",
    "ты крутой": "Спасибо за комплимент!",
    "сколько тебе лет": "Я только начинаю жить 😄",
    "кто тебя создал": "Это точно был не я)",
    "какой сегодня день": lambda: f"Сегодня {datetime.datetime.now().strftime('%d.%m.%Y')}",
    "какой час": lambda: f"Сейчас {datetime.datetime.now().strftime('%H:%M')}"
}


def get_main_keyboard():
    buttons = [
        ["🔍 Поиск", "❓ Помощь"],
        ["🔁 Перезапуск"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_attractions(city_name):
    url = "http://overpass-api.de/api/interpreter"

    query = f"""[out:json][timeout:25];
    area["name"="{city_name}"]->.searchArea;
    node["tourism"="attraction"](area.searchArea);
    out body;"""

    response = requests.post(url, data=query)

    if response.status_code != 200:
        print("Ошибка при запросе к Overpass API")
        return []
    data = response.json()
    return [item['tags'].get('name', 'Без названия') for item in data.get('elements', [])]


async def attractions(update, context):
    try:
        context2 = update.message.text.split()[1]
        response, counter, sett = list(), 75, set()

        for i, name in enumerate(get_attractions(context2), 1):
            if name != 'Без названия' and name not in sett:
                response.append(f"{i}. {name}")
                sett.add(name)
                counter -= 1
            if counter <= 0:
                break
        await update.message.reply_text(f'Конечно! Вот неплохая подборка достопримечательностей города {context2}:\n'+ '\n'.join(response))
    except:
        await update.message.reply_text('Ничего не нашлось')

async def geocoder(update, context):
    try:
        context2 = update.message.text.split()[1]
        geocoder_uri = "http://geocode-maps.yandex.ru/1.x/"
        response = await get_response(geocoder_uri, params={
            "apikey": "2546f784-26cb-4763-8fa4-c71067e1f0b9",
            "format": "json",
            "geocode": context2
        })

        # Проверка наличия ключа 'response'
        if "response" not in response:
            await update.message.reply_text("Ошибка: Нет данных в ответе от геокодера.")
            return

        toponym = response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
        ll, spn = get_ll_spn(toponym)

        static_api_request = f"http://static-maps.yandex.ru/1.x/?ll={ll}&spn={spn}&l=map"
        await context.bot.send_photo(
            update.message.chat_id,
            static_api_request,
            caption="Нашёл:"
        )
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")


def get_ll_spn(toponym):
    toponym_coodrinates = toponym["Point"]["pos"]
    toponym_longitude, toponym_lattitude = toponym_coodrinates.split(" ")

    ll = ",".join([toponym_longitude, toponym_lattitude])

    envelope = toponym["boundedBy"]["Envelope"]

    l, b = envelope["lowerCorner"].split(" ")
    r, t = envelope["upperCorner"].split(" ")

    dx = abs(float(l) - float(r)) / 2.0
    dy = abs(float(t) - float(b)) / 2.0

    span = f"{dx},{dy}"
    return ll, span


async def get_response(url, params):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            return await resp.json()


async def get_city_coords(city_name: str):
    async with httpx.AsyncClient() as client:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": city_name, "format": "json", "limit": 1}
        response = await client.get(url, params=params, headers={"User-Agent": "TelegramBot"})
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
        return None


async def get_poi(lat: float, lon: float):
    api_key = ""
    url = f"https://api.opentripmap.com/0.1/en/places/radius"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params={
            "apikey": api_key,
            "radius": 20000,
            "lat": lat,
            "lon": lon,
            "limit": 5
        })
        data = response.json()
        return [f"{place['name']} — {place.get('dist', 'N/A')} м" for place in data]


async def search_hotels(city: str):
    return [
        f"🏨 Отель {city} 1",
        f"🏨 Отель {city} 2",
        f"🏨 Отель {city} 3"
    ]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.message.from_user.id, None)  # очищаем состояние
    await update.message.reply_text(
        "Привет! Я помогу найти лучшие места для проживания и интересные места в городе.",
        reply_markup=get_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(('''/start — запустить бота
        /search — начать поиск
        /restart — перезапустить диалог
        Вы также можете использовать кнопки меню.'''))


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.message.from_user.id] = "awaiting_city"
    await update.message.reply_text("Введите название города:")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.message.from_user.id, None)
    await update.message.reply_text("Бот перезапущен.", reply_markup=get_main_keyboard())


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message = update.message.text.lower()
    if user_state.get(user_id) == "awaiting_city":
        city = update.message.text.strip()
        coords = await get_city_coords(city)
        if not coords:
            await update.message.reply_text("Не удалось определить координаты для этого города.")

        lat, lon = coords

        hotels = [
            f"🏨 Отель {city} 1",
            f"🏨 Отель {city} 2",
            f"🏨 Отель {city} 3"
        ]
        await update.message.reply_text("Рекомендованные отели:\n" + "\n".join(hotels))

        pois = await get_poi(lat, lon)
        await update.message.reply_text("Интересные места:\n" + "\n".join(pois))

        user_state.pop(user_id, None)

    elif 'покажи' in message:
        await geocoder(update, context)
    elif 'достопримечательности' in message:
        await attractions(update, context)
    elif 'погода в городе' in message:
        code_to_smile = {
            "Clear": "Ясно \U00002600",
            "Clouds": "Облачно \U00002601",
            "Rain": "Дождь \U00002614",
            "Drizzle": "Дождь \U00002614",
            "Thunderstorm": "Гроза \U000026A1",
            "Snow": "Снег \U0001F328",
            "Mist": "Туман \U0001F32B"
        }
        try:
            r = requests.get(
                f"http://api.openweathermap.org/data/2.5/weather?q={message.split()[3]}&appid={WEATHER_API_KEY}&units=metric"
            )
            data = r.json()

            city = data["name"]
            cur_weather = data["main"]["temp"]

            weather_description = data["weather"][0]["main"]
            if weather_description in code_to_smile:
                wd = code_to_smile[weather_description]
            else:
                wd = "Посмотри в окно, не пойму что там за погода!"

            humidity = data["main"]["humidity"]
            pressure = data["main"]["pressure"]
            wind = data["wind"]["speed"]
            sunrise_timestamp = datetime.datetime.fromtimestamp(data["sys"]["sunrise"])
            sunset_timestamp = datetime.datetime.fromtimestamp(data["sys"]["sunset"])
            length_of_the_day = datetime.datetime.fromtimestamp(
                data["sys"]["sunset"]) - datetime.datetime.fromtimestamp(
                data["sys"]["sunrise"])

            await update.message.reply_text(f"***{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}***\n"
                                            f"Погода в городе: {city}\nТемпература: {cur_weather}C° {wd}\n"
                                            f"Влажность: {humidity}%\nДавление: {pressure} мм.рт.ст\nВетер: {wind} м/с\n"
                                            f"Восход солнца: {sunrise_timestamp}\nЗакат солнца: {sunset_timestamp}\nПродолжительность дня: {length_of_the_day}"
                                            )

        except:
            await update.message.reply_text("\U00002620 Проверьте название города \U00002620")

    elif message == "🔍 поиск":
        await ask_city(update, context)
    elif message == "❓ помощь":
        await help_command(update, context)
    elif message == "🔁 перезапуск":
        await restart(update, context)


    elif any(greeting in message for greeting in GREETINGS):
        await update.message.reply_text("Здравствуйте! Чем могу помочь?")

    elif any(goodbye in message for goodbye in GOODBYES):
        await update.message.reply_text("До новых встреч!")

    elif 'посчитай' in message:
        try:
            await update.message.reply_text(eval(''.join(message.split()[1:])))
        except Exception:
            await update.message.reply_text('Извините, но вы указали неверный пример')

    elif message in CUSTOM_RESPONSES:
        response = CUSTOM_RESPONSES[message]
        if callable(response):
            response = response()
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Не понимаю. Напишите /help")


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", ask_city))
    application.add_handler(CommandHandler("restart", restart))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()