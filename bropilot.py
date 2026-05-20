from github import Github,GithubException
from github import Auth
import os
from dotenv import load_dotenv
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage
from pathlib import Path
import typer

CONFIG_DIR = Path.home() / ".config" / "bropilot"
ENV_FILE = CONFIG_DIR / ".env"

app = typer.Typer()


def first_time_setup():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    github_token = typer.prompt(
        "Enter GitHub Token",
        hide_input=False
    )

    google_api_key = typer.prompt(
        "Enter Google API Key",
        hide_input=False
    )

    ENV_FILE.write_text(
        f"GITHUB_TOKEN={github_token}\n"
        f"GOOGLE_API_KEY={google_api_key}\n"
    )

    print("\nSetup complete.\n")



if not ENV_FILE.exists():
    first_time_setup()

load_dotenv(ENV_FILE)

load_dotenv()
token=os.getenv("GITHUB_TOKEN")
API_KEY=os.getenv("GOOGLE_API_KEY")

auth=Auth.Token(token)

g=Github(auth=auth, lazy=True)
user=g.get_user()

rep=user.get_repo("rss")





def _get_repo(repo_name: str):
    """Fetch a repo by name (owner/repo or bare name)."""
    if "/" in repo_name:
        return g.get_repo(repo_name)
    return user.get_repo(repo_name)




@tool
def get_all_repositories() -> list:
    """
    Return a list of all GitHub repositories owned by the authenticated user.
    Use this to check whether a repository already exists before creating one.
    """
    try:
        print('fetching repos')
        repos = user.get_repos()
        print('processing repos')
        return [
            {
                "name":        r.name,
                "full_name":   r.full_name,
                "private":     r.private,
                "description": r.description or "",
                "url":         r.html_url,
                "stars":       r.stargazers_count,
                "language":    r.language or "N/A",
            }
            for r in repos
        ]
    except GithubException as e:
        return {"error": str(e)}


@tool
def get_repository_info(repo_name: str) -> dict:
    """
    Get detailed information about a specific repository.
    repo_name: repository name (e.g. ' chat_rss') or full name (e.g. 'owner/my-repo').
    """
    try:
        print('getting repo info')
        r = _get_repo(repo_name)
        print('info received')
        return {
            "name":             r.name,
            "full_name":        r.full_name,
            "description":      r.description or "",
            "private":          r.private,
            "url":              r.html_url,
            "clone_url":        r.clone_url,
            "default_branch":   r.default_branch,
            "stars":            r.stargazers_count,
            "forks":            r.forks_count,
            "open_issues":      r.open_issues_count,
            "language":         r.language or "N/A",
            "topics":           r.get_topics(),
            "created_at":       str(r.created_at),
            "updated_at":       str(r.updated_at),
        }
    except GithubException as e:
        return {"error": str(e)}



@tool
def create_repository(repo_name: str, description: str = "", private: bool = False) -> dict:
    """
    Create a new GitHub repository for the authenticated user.
    repo_name   : name of the new repository.
    description : short description (optional).
    private     : True to make it private, False (default) for public.
    """
    try:
        repo = user.create_repo(
            name=repo_name,
            description=description,
            private=private,
            auto_init=True,
        )
        return {"success": True, "name": repo.name, "url": repo.html_url, "private": repo.private}
    except GithubException as e:
        return {"error": str(e)}
    


def delete_repository(repo_name: str) -> dict:
    """
    Permanently delete a repository. Use with caution — this is irreversible.
    repo_name: repository name or full name.
    """
    try:
        repo = _get_repo(repo_name)
        repo.delete()
        return {"success": True, "message": f"Repository '{repo_name}' deleted."}
    except GithubException as e:
        return {"error": str(e)}


@tool
def list_repository_files(repo_name: str, path: str = "") -> list:
    """
    List files and folders at a given path inside a repository.
    repo_name: repository name or full name.
    path     : sub-directory path (default is root "").
    """
    try:
        repo     = _get_repo(repo_name)
        contents = repo.get_contents(path)
        return [{"name": c.name, "type": c.type, "path": c.path, "size": c.size} for c in contents]
    except GithubException as e:
        return {"error": str(e)}
    

@tool
def create_or_update_file(repo_name: str, file_path: str, content: str,
                          commit_message: str, branch: str = "main") -> dict:
    """
    Create a new file or update an existing file in a repository.
    repo_name      : repository name or full name.
    file_path      : path where the file will be saved (e.g. 'docs/README.md').
    content        : plain-text content to write.
    commit_message : git commit message.
    branch         : target branch (default 'main').
    """
    try:
        repo    = _get_repo(repo_name)
        encoded = content.encode("utf-8")
        try:
            existing = repo.get_contents(file_path, ref=branch)
            result = repo.update_file(file_path, commit_message, encoded,
                                      existing.sha, branch=branch)
            action = "updated"
        except GithubException:
            result = repo.create_file(file_path, commit_message, encoded, branch=branch)
            action = "created"
        return {"success": True, "action": action, "path": file_path,
                "commit_sha": result["commit"].sha}
    except GithubException as e:
        return {"error": str(e)}


@tool
def delete_file(repo_name: str, file_path: str, commit_message: str,
                branch: str = "main") -> dict:
    """
    Delete a file from a repository.
    repo_name      : repository name or full name.
    file_path      : path of the file to delete.
    commit_message : git commit message.
    branch         : target branch (default 'main').
    """
    try:
        repo    = _get_repo(repo_name)
        content = repo.get_contents(file_path, ref=branch)
        repo.delete_file(file_path, commit_message, content.sha, branch=branch)
        return {"success": True, "deleted": file_path}
    except GithubException as e:
        return {"error": str(e)}
    

SYSTEM_PROMPT = f"""You are a helpful GitHub assistant for the user '{user.login}'.
You can manage repositories, files.

Guidelines:
- Always confirm destructive actions (delete, merge) before proceeding if unsure.
- Use get_all_repositories to verify whether a repo exists before creating one.
- Present results clearly and concisely.
- If a tool returns an 'error' key, explain the problem and suggest a fix.
"""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=API_KEY,
    temperature=0
)

agent = create_react_agent(
    model=llm,
    tools=[_get_repo,create_or_update_file,create_repository,delete_file,get_repository_info
           ,get_all_repositories]
)



def extract_agent_reply(response: dict) -> str:
    for msg in reversed(response["messages"]):
        if not isinstance(msg, AIMessage) or not msg.content:
            continue
        content = msg.content
        # Gemini with tool use returns a list of dicts
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            text = "\n".join(p for p in parts if p).strip()
            if text:
                return text
        # Plain string (no tools used)
        elif isinstance(content, str):
            return content.strip()
    return "(no response)"


@app.command()
def main(prompt: str):
    print('bropilot thinking....')
    print('invoking tools')
    response = agent.invoke({
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    })

    reply = extract_agent_reply(response)

    print(f"\nbropilot:\n{reply}\n")
    print("-" * 60)

if __name__ == "__main__":
    app()