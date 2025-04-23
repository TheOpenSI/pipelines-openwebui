
import re
import sys, os, dotenv, shutil, yaml
from turtle import pos
import pandas as pd
import requests

# Add CoSMIC to the system path
ROOT = os.path.abspath(f"{os.path.dirname(os.path.abspath(__file__))}/../../../..")
sys.path.append(ROOT)

# from src.opensi_cosmic import OpenSICoSMIC
from pydantic import BaseModel
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

baseUrl = "http://localhost:8000"

# response = requests.get(f"{baseUrl}/config")
# result = response.json()["result"]
# print(result["query_analyser"]["llm_name"])

response = requests.post(
    f"{baseUrl}/cosmic",
    json={"user_message": "Hello, how can you help me?"}
)
print(response.text)
if response.status_code == 200:
    print(response.json())




class Pipeline:
    class Valves(BaseModel):
        pass

    # A class-level dictionary to keep track of user queries. 
    # Key: user_id, Value: number of queries asked.
    user_queries_count = {}

    def __init__(self):
        self.name = "OpenSI-CoSMIC"
        self.root = ROOT
        self.config_path = os.path.join(self.root, "scripts/configs/config_updated.yaml")
        self.env_path = os.path.abspath(os.path.join(self.root, ".env"))
        self.statistic_dir = os.path.join(self.root, "data/cosmic/statistic")
        self.statistic_dict = {
            "user_id": "unknown",
            "email": "unknown",
            "start_date": -1,
            "last_date": -1,
            "average_token_length": 0,
            "query_count": 0
        }

        if not os.path.exists(self.config_path):
            config_path = os.path.join(self.root, "scripts/configs/config.yaml")
            shutil.copyfile(config_path, self.config_path)

        self.config_modify_timestamp = str(os.path.getmtime(self.config_path))
        self.MAX_QUERIES_PER_USER = 5

        # Check if vector database is valid.
        with open(self.config_path, "r") as file:
            config = yaml.safe_load(file)

        if not os.path.exists(config["rag"]["vector_db_path"]):
            config["rag"]["vector_db_path"] = \
                f"{self.root}/data/cosmic/vector_db_cosmic"

        with open(self.config_path, "w") as file:
            yaml.safe_dump(config, file)

        # Set OPENAI_API_KEY first before constructing OpenSICoSMIC since this config will
        # be directly used in OpenSICoSMIC().
        self.update_openai_key()
        # self.opensi_cosmic = OpenSICoSMIC(config_path=self.config_path)
        self.openai_api_status = self.check_openai_key()

    def update_openai_key(self):
        # Set up OPENAI_API_KEY globally through root's .env.
        envs = dotenv.dotenv_values(self.env_path)

        if "OPENAI_API_KEY" in envs.keys():
            self.openai_api_key = envs["OPENAI_API_KEY"]
        else:
            self.openai_api_key = ""

        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        self.valves = self.Valves(**{"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")})

    def check_openai_key(self):
        try:
            response = requests.get(f"{baseUrl}/config")
            if response.status_code != 200:
                raise Exception(f"Error fetching config from the server. Status code: {response.status_code}")
            config = response.json()["result"]
            llm_name = config["llm_name"]
            query_analyser_llm_name = config["query_analyser"]["llm_name"]

            # llm_name = self.opensi_cosmic.config.llm_name
            # query_analyser_llm_name = self.opensi_cosmic.config.query_analyser.llm_name

            is_llm_name_gpt = llm_name.find("gpt") > -1
            is_query_analyser_llm_name_gpt = query_analyser_llm_name.find("gpt") > -1

            llm_name_list = []
            if is_llm_name_gpt: llm_name_list.append(llm_name)
            if is_query_analyser_llm_name_gpt and (query_analyser_llm_name not in llm_name_list):
                llm_name_list.append(query_analyser_llm_name)

            count = len(llm_name_list)

            if (count > 0) and (self.openai_api_key == ""):
                if count == 1: answer = f"{llm_name_list[0]} is"
                elif count == 2: answer = f"{llm_name_list[0]} and {llm_name_list[1]} are"
                answer = f"Since {answer} used, please add valid OPENAI_API_KEY\n" \
                    f"in [account]/Settings/Admin Settings/Configs/[OpenAI API Key] then save."
            else:
                answer = ""

            return answer
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching config from the server: {e}")

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        try:
            response = requests.get(f"{baseUrl}/quit")
            if response.status_code != 200:
                raise Exception(f"Error during /quit API call: {response.text}")
            print(response.json()["message"])
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error during /quit API call: {e}")
        # self.opensi_cosmic.quit()

    def update_statistic_table(
        self,
        statistic_dict
    ):
        os.makedirs(self.statistic_dir, exist_ok=True)
        current_time = statistic_dict["last_date"]
        time_split = current_time.split(",")[0].split("-")
        current_month_year = f"{time_split[1]}-{time_split[2]}"
        statistic_path = os.path.join(
            self.statistic_dir,
            f"{current_month_year}.csv"
        )

        if os.path.exists(statistic_path):
            data = pd.read_csv(statistic_path)
            user_emails = data["email"].tolist()
        else:
            user_emails = []

        if statistic_dict["email"] in user_emails:
            idx = [idx for idx, user_email in enumerate(user_emails) if user_email == statistic_dict["email"]][0]
            data.loc[idx, "last_date"] = statistic_dict["last_date"]
            history_total_token_length = data["average_token_length"][idx] * data["query_count"][idx]
            current_total_token_length = statistic_dict["average_token_length"] * statistic_dict["query_count"]
            total_query_count = data["query_count"][idx] + statistic_dict["query_count"]
            data.loc[idx, "average_token_length"] = (history_total_token_length + current_total_token_length) / total_query_count
            data.loc[idx, "query_count"] = total_query_count
        else:
            df = pd.DataFrame([{
                "user_id": statistic_dict["user_id"],
                "email": statistic_dict["email"],
                "start_date": statistic_dict["start_date"],
                "last_date": statistic_dict["last_date"],
                "average_token_length": statistic_dict["average_token_length"],
                "query_count": statistic_dict["query_count"]
            }])
            if len(user_emails) > 0: df = pd.concat([data, df], axis=0)
            data = df

        data.to_csv(
            statistic_path,
            header=[
                "user_id",
                "email",
                "start_date",
                "last_date",
                "average_token_length",
                "query_count"
            ],
            index=False
        )

    def update_statistic_per_query(
        self,
        query,
        user_id,
        user_email,
        current_time
    ):
        if False:
            # Save for the previous user (when the user_id changed).
            pre_user_id = self.statistic_dict["user_id"]
            pre_query_count = self.statistic_dict["query_count"]
            token_length = len(query)

            # Accumulate for the same user.
            if pre_user_id == user_id:
                pre_average_token_length = self.statistic_dict["average_token_length"]
                self.statistic_dict["last_date"] = current_time
                self.statistic_dict["average_token_length"] = \
                    (pre_average_token_length * pre_query_count + token_length) \
                    / (pre_query_count + 1)
                self.statistic_dict["query_count"] = pre_query_count + 1

            if pre_user_id != user_id:
                # Save previous user statistic.
                if pre_user_id != "unknown":
                    self.update_statistic_table(self.statistic_dict)

                # Initialize for a different user.
                self.statistic_dict["user_id"] = user_id
                self.statistic_dict["email"] = user_email
                self.statistic_dict["start_date"] = current_time
                self.statistic_dict["last_date"] = current_time
                self.statistic_dict["average_token_length"] = token_length
                self.statistic_dict["query_count"] = 1
        else:
            # Save every query for the current user.
            token_length = len(query)
            self.statistic_dict["user_id"] = user_id
            self.statistic_dict["email"] = user_email
            self.statistic_dict["start_date"] = current_time
            self.statistic_dict["last_date"] = current_time
            self.statistic_dict["average_token_length"] = token_length
            self.statistic_dict["query_count"] = 1
            self.update_statistic_table(self.statistic_dict)

    def post_to_cosmic(self, user_message: str) -> str:
        try:
            response = requests.post(
                f"{baseUrl}/cosmic",
                json={"user_message": user_message}
            )
            if response.status_code == 200:
                return response.json()["result"]
            
            raise Exception(f"Error: {response.status_code}, {response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error during /cosmic API call: {e}")

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict
    ):
        # Some will run twice for history, just ignore.
        if user_message[:3] == "###": return ""

        current_config_modify_timestamp = str(os.path.getmtime(self.config_path))
        current_openai_api_key = os.environ["OPENAI_API_KEY"]

        if (current_config_modify_timestamp != self.config_modify_timestamp) \
            or (current_openai_api_key != self.openai_api_key):
            self.on_shutdown()
            # self.opensi_cosmic.quit()
            self.openai_api_key = current_openai_api_key
            self.config_modify_timestamp = current_config_modify_timestamp
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
            # self.opensi_cosmic = OpenSICoSMIC(config_path=self.config_path)
            print('Reconstruct OpenSICoSMIC due to changed configs.')
            self.update_openai_key()
            self.openai_api_status = self.check_openai_key()

        # Extract user_id from body. Adjust if user_id is available elsewhere.
        user_id = body["user"]["id"]
        user_role = body["user"]["role"]
        user_email = body["user"]["email"]

        # Set user ID to use a specific vector database.
        # For the same user, the QA instance will not change.
        # self.opensi_cosmic.set_up_qa(str(user_id))

        try:
            response = requests.get(f"{baseUrl}/setup-qa/{str(user_id)}")
            if response.status_code != 200:
                raise Exception(f"Error during /setup-qa API call: {response.text}")
            print(response.json().message)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error during /setup-qa API call: {e}")

        # Check how many queries this user has already made.
        current_count = self.user_queries_count.get(user_id, 0)

        # Compute statistic information.
        current_time = datetime.strftime(
            datetime.now(tz=ZoneInfo("Australia/Sydney")),
            '%d-%m-%Y,%H:%M:%S'
        )
        self.update_statistic_per_query(
            user_message,
            user_id,
            user_email,
            current_time
        )

        if (user_role != "admin") and (current_count >= self.MAX_QUERIES_PER_USER):
            # Return a message indicating the limit has been reached
            return "You have reached the maximum number of queries allowed."

        # Increment the count for this user
        self.user_queries_count[user_id] = current_count + 1

        # Proceed as normal
        if self.openai_api_status != "":
            answer = self.openai_api_status
        else:
            # Find the key word for adding file to vector database.
            if user_message.find("</files>") > -1:
                splits = user_message.split("</files>")

                # Extract the original question.
                user_message = splits[1]

                # The directory storing uploaded files.
                file_dir = f"{self.root}/data/cosmic/backend/uploads/{user_id}"

                # Extract the files.
                files = splits[0].split("<files>")[-1]
                files = [os.path.join(file_dir, v) for v in files.split(',') if v != ""]

                for file in files:
                    # Form a prompt to update vector database.
                    user_message_vector_db_update = \
                        f"Add the following file to the vector database: {file}"

                    # Update vector database.
                    # answer = self.opensi_cosmic(user_message_vector_db_update)[0]
                    answer = self.post_to_cosmic(user_message_vector_db_update)

            answer = self.post_to_cosmic(user_message)
            if answer is None: answer = 'Successfully!'

        return answer
