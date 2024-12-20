"""Initialize and manage Ansible playbooks.

This module handles the initialization and management of Ansible playbooks,
including cloning from a Git repository, installing Galaxy requirements,
and verifying playbook configurations. It supports both default playbooks
and custom configurations through environment variables.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import ansible_runner
import git
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PLAYBOOKS = {
    "create_cluster": {
        "name": "create_cluster.yml",
        "required": True,
        "description": "Creates a new Kubernetes cluster",
        "variables": [
            "cluster_name",
            "service_account",
            "kubeconfig_vault_path",
            "force",
            "overwrite",
            "vault_token",
        ],
    },
    "update_service_account": {
        "name": "update_service_account.yml",
        "required": True,
        "description": "Updates service account credentials",
        "variables": ["cluster_name", "service_account", "overwrite", "vault_token"],
    },
}


class PlaybookConfig:
    """Configuration wrapper for individual Ansible playbooks.

    This class provides a structured way to manage playbook configurations,
    including metadata about the playbook's requirements and variables.

    Attributes:
        name (str): Identifier for the playbook.
        filename (str): Actual filename of the playbook.
        required (bool): Whether the playbook is required for system operation.
        description (str): Human-readable description of the playbook's purpose.
        variables (list): Required variables for playbook execution.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize a playbook configuration.

        Args:
            name (str): Identifier for the playbook.
            config (Dict[str, Any]): Configuration dictionary containing playbook metadata.
        """
        self.name = name
        self.filename = config.get("name", f"{name}.yml")
        self.required = config.get("required", False)
        self.description = config.get("description", "")
        self.variables = config.get("variables", [])

    def to_dict(self) -> Dict[str, Any]:
        """Convert the configuration to a dictionary.

        Returns:
            Dict[str, Any]: Dictionary representation of the playbook configuration.
        """
        return {
            "name": self.filename,
            "required": self.required,
            "description": self.description,
            "variables": self.variables,
        }


class AnsibleInitializer:
    """Handles initialization and management of Ansible playbooks.

    This class manages the lifecycle of Ansible playbooks, including repository
    cloning, dependency installation, and configuration verification. It supports
    both default playbooks and custom configurations through environment variables.

    Attributes:
        playbooks_dir (str): Directory where playbooks are stored.
        gitea_url (str): Base URL for the Gitea server.
        gitea_token (str): Authentication token for Gitea.
        repo_name (str): Name of the playbooks repository.
        collections_path (str): Path to Ansible collections.
        roles_path (str): Path to Ansible roles.
        playbooks (Dict[str, PlaybookConfig]): Loaded playbook configurations.
    """

    def __init__(self):
        """Initialize the Ansible environment setup."""
        self.playbooks_dir = os.environ.get("PLAYBOOKS_DIR", "/app/playbooks")
        self.gitea_url = os.environ.get("GITEA_URL", "http://gitea:3000")
        self.gitea_token = os.environ.get("GITEA_TOKEN")
        self.repo_name = os.environ.get("GITEA_PLAYBOOKS_REPO", "user/pxbackup-playbooks")

        # Create necessary directories
        self.collections_path = os.path.join(self.playbooks_dir, "collections")
        self.roles_path = os.path.join(self.playbooks_dir, "roles")
        Path(self.collections_path).mkdir(parents=True, exist_ok=True)
        Path(self.roles_path).mkdir(parents=True, exist_ok=True)

        # Load playbook configuration
        self.playbooks = self.load_playbook_config()

    def load_playbook_config(self) -> Dict[str, PlaybookConfig]:
        """Load playbook configuration from environment or file.

        This method attempts to load playbook configurations from environment variables
        or a configuration file. If neither is available, it falls back to default
        configurations.

        Returns:
            Dict[str, PlaybookConfig]: Loaded playbook configurations.
        """
        playbooks = {}

        # Try loading from environment variable
        playbooks_json = os.environ.get("ANSIBLE_PLAYBOOKS")
        if playbooks_json:
            try:
                config = json.loads(playbooks_json)
                for _name, pb_config in config.items():
                    playbooks[_name] = PlaybookConfig(_name, pb_config)
                logger.info("Loaded playbook configuration from environment")
                return playbooks
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse ANSIBLE_PLAYBOOKS environment variable: {e}")

        # Try loading from config file
        config_path = os.path.join(self.playbooks_dir, "playbooks.yml")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                for _name, pb_config in config.items():
                    playbooks[_name] = PlaybookConfig(_name, pb_config)
                logger.info("Loaded playbook configuration from playbooks.yml")
                return playbooks
            except Exception as e:
                logger.warning(f"Failed to load playbooks.yml: {e}")

        # Fall back to default configuration
        logger.info("Using default playbook configuration")
        for _name, config in DEFAULT_PLAYBOOKS.items():
            playbooks[_name] = PlaybookConfig(_name, config)

        return playbooks

    def get_repo_url(self) -> str:
        """Get repository URL with authentication if token is provided.

        Returns:
            str: Repository URL.
        """
        base_url = f"{self.gitea_url}/{self.repo_name}.git"
        if self.gitea_token:
            if "://" in base_url:
                protocol, rest = base_url.split("://", 1)
                return f"{protocol}://oauth2:{self.gitea_token}@{rest}"
            return base_url
        return base_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def clone_or_pull_repo(self) -> None:
        """Clone or pull the playbooks repository.

        This method attempts to clone or pull the playbooks repository from the
        specified Gitea server. If the repository does not exist, it creates a
        default repository structure.

        Raises:
            Exception: If the repository operation fails.
        """
        try:
            repo_url = self.get_repo_url()

            if os.path.exists(os.path.join(self.playbooks_dir, ".git")):
                logger.info("Repository exists, pulling latest changes...")
                repo = git.Repo(self.playbooks_dir)
                origin = repo.remotes.origin
                origin.pull()
            else:
                logger.info("Cloning repository...")
                git.Repo.clone_from(repo_url, self.playbooks_dir)

            logger.info("Repository sync completed successfully")
        except git.GitCommandError as e:
            if "Repository not found" in str(e):
                logger.info("Repository doesn't exist, creating default structure...")
                self.create_default_repo()
            else:
                logger.error(f"Git operation failed: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Failed to sync repository: {str(e)}")
            raise

    def create_default_repo(self) -> None:
        """Create default repository structure with essential playbooks.

        This method creates a default repository structure with essential playbooks
        if the repository does not exist.

        Raises:
            Exception: If the repository creation fails.
        """
        try:
            # Create local repository
            repo = git.Repo.init(self.playbooks_dir)

            # Create default playbooks
            for _name, config in DEFAULT_PLAYBOOKS.items():
                playbook_path = os.path.join(self.playbooks_dir, config["name"])
                with open(playbook_path, "w") as f:
                    yaml.safe_dump(
                        [
                            {
                                "name": config["description"],
                                "hosts": "localhost",
                                "gather_facts": False,
                                "vars": {var: "{{ " + var + " }}" for var in config["variables"]},
                                "tasks": [
                                    {
                                        "name": "Placeholder task",
                                        "debug": {"msg": ("Placeholder playbook - " "replace with actual tasks")},
                                    }
                                ],
                            }
                        ],
                        f,
                    )

            # Create requirements files
            collections_path = os.path.join(self.playbooks_dir, "collections/requirements.yml")
            roles_path = os.path.join(self.playbooks_dir, "roles/requirements.yml")

            Path(collections_path).parent.mkdir(parents=True, exist_ok=True)
            Path(roles_path).parent.mkdir(parents=True, exist_ok=True)

            with open(collections_path, "w") as f:
                yaml.safe_dump({"collections": []}, f)

            with open(roles_path, "w") as f:
                yaml.safe_dump({"roles": []}, f)

            # Create inventory
            inventory_path = os.path.join(self.playbooks_dir, "inventory/hosts.yml")
            Path(inventory_path).parent.mkdir(parents=True, exist_ok=True)
            with open(inventory_path, "w") as f:
                yaml.safe_dump(
                    {
                        "all": {
                            "children": {
                                "k8s_clusters": {
                                    "hosts": {},
                                    "vars": {"ansible_connection": "local"},
                                }
                            }
                        }
                    },
                    f,
                )

            # Commit and push if we have credentials
            repo.index.add("*")
            repo.index.commit("Initial commit with default playbooks")

            if self.gitea_token:
                repo.create_remote("origin", self.get_repo_url())
                repo.remotes.origin.push("master")
                logger.info("Created and pushed default repository structure")
            else:
                logger.warning("No Gitea token provided, skipping repository push")

        except Exception as e:
            logger.error(f"Failed to create default repository: {str(e)}")
            raise

    def read_requirements(self) -> Dict[str, List[str]]:
        """Read requirements files for collections and roles.

        Returns:
            Dict[str, List[str]]: Dictionary of requirements for collections and roles.
        """
        requirements = {"collections": [], "roles": []}

        # Read collections requirements
        collections_req = os.path.join(self.playbooks_dir, "collections/requirements.yml")
        if os.path.exists(collections_req):
            with open(collections_req) as f:
                try:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "collections" in data:
                        requirements["collections"] = data["collections"]
                    elif isinstance(data, list):
                        requirements["collections"] = data
                except yaml.YAMLError as e:
                    logger.error(f"Error parsing collections requirements: {str(e)}")

        # Read roles requirements
        roles_req = os.path.join(self.playbooks_dir, "roles/requirements.yml")
        if os.path.exists(roles_req):
            with open(roles_req) as f:
                try:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "roles" in data:
                        requirements["roles"] = data["roles"]
                    elif isinstance(data, list):
                        requirements["roles"] = data
                except yaml.YAMLError as e:
                    logger.error(f"Error parsing roles requirements: {str(e)}")

        return requirements

    def install_galaxy_requirements(self, requirements: Dict[str, List[str]]) -> None:
        """Install Ansible Galaxy requirements.

        Args:
            requirements (Dict[str, List[str]]): Dictionary of requirements for
                collections and roles.
        """
        try:
            # Install collections
            if requirements["collections"]:
                logger.info("Installing Ansible collections...")
                collection_args = [
                    "ansible-galaxy",
                    "collection",
                    "install",
                    "-f",
                    "-p",
                    self.collections_path,
                ]

                for collection in requirements["collections"]:
                    if isinstance(collection, dict):
                        collection_name = collection.get("name")
                        collection_version = collection.get("version", "*")
                        if collection_name:
                            collection_args.append(f"{collection_name}:{collection_version}")
                    else:
                        collection_args.append(collection)

                subprocess.run(collection_args, check=True)

            # Install roles
            if requirements["roles"]:
                logger.info("Installing Ansible roles...")
                role_args = [
                    "ansible-galaxy",
                    "role",
                    "install",
                    "-f",
                    "-p",
                    self.roles_path,
                ]

                for role in requirements["roles"]:
                    if isinstance(role, dict):
                        role_name = role.get("name")
                        role_version = role.get("version", "*")
                        if role_name:
                            role_args.append(f"{role_name}:{role_version}")
                    else:
                        role_args.append(role)

                subprocess.run(role_args, check=True)

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Galaxy requirements: {str(e)}")
            raise

    def verify_playbooks(self) -> None:
        """Verify required playbooks exist and are valid.

        Raises:
            FileNotFoundError: If required playbooks are missing.
        """
        missing_required = []

        for _name, playbook in self.playbooks.items():
            if not playbook.required:
                continue

            playbook_path = os.path.join(self.playbooks_dir, playbook.filename)
            if not os.path.exists(playbook_path):
                missing_required.append(playbook.filename)
                continue

            try:
                # Validate playbook syntax
                runner = ansible_runner.Runner(
                    playbook=playbook_path,
                    private_data_dir=os.environ.get("RUNNER_PATH", "/runner"),
                    quiet=True,
                )
                runner.run()
                logger.info(f"Validated playbook: {playbook.filename}")
            except Exception as e:
                logger.error(f"Failed to validate playbook {playbook.filename}: {str(e)}")
                raise

        if missing_required:
            raise FileNotFoundError(f"Required playbooks not found: {', '.join(missing_required)}")

    def save_playbook_config(self) -> None:
        """Save current playbook configuration to file."""
        config = {_name: playbook.to_dict() for _name, playbook in self.playbooks.items()}

        config_path = os.path.join(self.playbooks_dir, "playbooks.yml")
        with open(config_path, "w") as f:
            yaml.safe_dump(config, f)
        logger.info("Saved playbook configuration to playbooks.yml")

    def initialize(self) -> bool:
        """Start the initialization process.

        Returns:
            bool: Whether the initialization was successful.
        """
        try:
            logger.info("Starting Ansible initialization...")

            # Clone or pull repository
            self.clone_or_pull_repo()

            # Read and install Galaxy requirements
            requirements = self.read_requirements()
            self.install_galaxy_requirements(requirements)

            # Verify playbooks
            self.verify_playbooks()

            # Save configuration if it was loaded from defaults
            if not os.path.exists(os.path.join(self.playbooks_dir, "playbooks.yml")):
                self.save_playbook_config()

            logger.info("Ansible initialization completed successfully")
            return True
        except Exception as e:
            logger.error(f"Ansible initialization failed: {str(e)}")
            raise


def init_playbooks():
    """Initialize Ansible playbooks.

    Returns:
        bool: Whether the initialization was successful.
    """
    initializer = AnsibleInitializer()
    return initializer.initialize()


if __name__ == "__main__":
    init_playbooks()
