from langgraph.prebuilt import create_react_agent
import boto3, requests, os
from dotenv import load_dotenv
from typing import List, Optional, TypedDict, Union, Literal
from langgraph.checkpoint.memory import InMemorySaver


from typing import Callable
from langchain_core.tools import BaseTool, tool as create_tool
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt 
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt

checkpointer = InMemorySaver()
load_dotenv()
api_key = os.getenv("EMAIL_DISPATCHER_API_KEY")


# class HumanInterruptConfig(TypedDict):
#     allow_ignore: bool
#     allow_respond: bool
#     allow_edit: bool
#     allow_accept: bool


# class ActionRequest(TypedDict):
#     action: str
#     args: dict

# class HumanInterrupt(TypedDict):
#     action_request: ActionRequest
#     config: HumanInterruptConfig
#     description: Optional[str]


# class HumanResponse(TypedDict):
#     type: Literal['accept', 'ignore', 'response', 'edit']
#     args: Union[None, str, ActionRequest]



def add_human_in_the_loop(
    tool: Callable | BaseTool,
    *,
    interrupt_config: HumanInterruptConfig = None,
) -> BaseTool:
    """Wrap a tool to support human-in-the-loop review.""" 
    if not isinstance(tool, BaseTool):
        tool = create_tool(tool)
        print(f"Wrapped tool: {tool.name} with description: {tool.description}")

    if interrupt_config is None:
        interrupt_config = {
            "allow_accept": True,
            "allow_edit": True,
            "allow_respond": True,
            "allow_ignore": True
        }
        print("Using default interrupt configuration.")

    @create_tool(  
        tool.name,
        description=tool.description,
        args_schema=tool.args_schema
    )
    def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        request: HumanInterrupt = {
            "action_request": {
                "action": tool.name,
                "args": tool_input
            },
            "config": interrupt_config,
            "description": "Please review the tool call"
        }
        response = interrupt([request])[0]  
        # approve the tool call
        if response["type"] == "accept":
            tool_response = tool.invoke(tool_input, config)
        # update tool call args
        elif response["type"] == "edit":
            tool_input = response["args"]["args"]
            tool_response = tool.invoke(tool_input, config)
        # respond to the LLM with user feedback
        elif response["type"] == "response":
            user_feedback = response["args"]
            tool_response = user_feedback
        else:
            raise ValueError(f"Unsupported interrupt response type: {response['type']}")

        return tool_response

    return call_tool_with_interrupt


# def fetch_email(bucket: str = "malkom-dev-poc", key: str = "Vanraj/sample_email_chain.html") -> str:
#     """
#     Fetch the content of an email stored as an HTML file in an AWS S3 bucket.

#     This function retrieves the HTML content of an email stored in S3.

#     Args:
#         bucket (str, optional): The name of the S3 bucket where the email HTML file is stored.
#             Defaults to "malkom-dev-poc".
#         key (str, optional): The key (file path within the bucket) of the HTML file to fetch.
#             Defaults to "Vanraj/sample_email_chain.html".

#     Returns:
#         str: The decoded HTML content of the file if successful.
#              Returns an error message string if the operation fails.
#     """
#     s3_client = boto3.client('s3')
#     try:
#         response = s3_client.get_object(Bucket=bucket, Key=key)
#         email_content = response['Body'].read().decode('utf-8')
#         return email_content
#     except Exception as e:
#         return f"Error fetching email: {str(e)}"
    

def fetch_email_from_file(
    filepath: str = "dummy_files/sample_email_chain.html"
) -> str:
    """
    Fetch the content of an email stored as an HTML file from the local file system.

    Args:
        filepath (str, optional): The relative path to the HTML file within the project.
            Defaults to "dummy_files/sample_email_chain.html".

    Returns:
        str: The HTML content of the email file if successful.
             Returns an error message string if the operation fails.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return f"File not found: {filepath}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def send_email_reply(
    taskid: str,
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    sender: str = "donotreply@one-line.com"
) -> str:
    """
    Sends an email reply using the Integration HUB Email Dispatcher API Gateway.

    Args:
        taskid (str): Unique identifier for tracking the email task.
        to (List[str]): List of recipient email addresses.
        subject (str): Subject line of the email.
        body (str): Body of the email in plain text or HTML.
        cc (List[str], optional): List of CC email addresses. Defaults to None.
        sender (str, optional): Sender's email address. Defaults to "donotreply@one-line.com".

    Returns:
        str: Success message if sent, or an error message.
    """
    url = "https://ohr3iawb7d.execute-api.ap-southeast-1.amazonaws.com/dev/email-dispatcher"
    api_key = os.getenv("EMAIL_DISPATCHER_API_KEY")

    if not api_key:
        return "Missing EMAIL_DISPATCHER_API_KEY environment variable."

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    email_data = {
        "taskid": taskid,
        "to": to,
        "cc": cc or [],
        "from": sender,
        "subject": subject,
        "body": body
    }

    try:
        response = requests.post(url, json=[email_data], headers=headers, timeout=10)
        response.raise_for_status()
        return f"Email sent successfully to {', '.join(to)}"
    except requests.exceptions.RequestException as e:
        return f"Failed to send email: {str(e)}"

graph = create_react_agent(
    model="gpt-4o",
    tools=[fetch_email_from_file, add_human_in_the_loop(send_email_reply)],
    prompt="You are a helpful assistant"
)