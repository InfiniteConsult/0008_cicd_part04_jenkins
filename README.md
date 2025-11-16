# Chapter 1: The Challenge: Our Code is Just Sitting on a Shelf

In our last article, we built our "Central Library," a secure, self-hosted GitLab instance. This was a massive step forward. Our code—including our polyglot "hero project"—is now version-controlled, secure, and stored in a central, trusted location. But this success has also revealed our next, and most obvious, challenge: our code is just *sitting there*.

It's inert. A developer can `git push` a new feature, but nothing *happens*. The connection between our code repository and an actual build process is completely missing. We have a fantastic source of truth, but no *action*.

## Deconstructing the "It Works On My Machine" Flaw

Without an automated system, we are forced to fall back on a manual build process. A developer would clone the repository, run `./setup.sh` on their local workstation, and then run `./run-coverage.sh`. This "manual build" process is fraught with problems that prevent any real, scalable development.

The most famous of these is the "it works on my machine" flaw. This isn't just a meme; it's a critical business risk that stems from two core issues:

1.  **Environment Inconsistency:** My workstation is not identical to yours. I might be running a slightly different version of `cmake`, a newer patch of the Rust toolchain, or a different set of Python libraries. A build that succeeds for me might fail for you simply because our environments have "drifted" apart. This makes it impossible to guarantee that a given commit is truly stable.
2.  **Lack of Auditability:** The manual build process is a black hole. There is no central, immutable record of *who* built *what*, *when*. Which commit was used for the "release" binary that was just emailed to the client? Was it built with the latest changes? Was it built in "Debug" or "Release" mode? Did all the tests *actually* pass, or did the developer just *say* they did? We have no way to know.

This manual, unscalable process is unacceptable. We need a centralized, automated orchestrator that can act as the "brain" of our entire operation.

## The Solution: An Automated "Factory Foreman"

This is where we introduce **Jenkins**. Jenkins will be the "Factory Foreman" for our CI/CD city.

Its job is to watch our "Central Library" (GitLab) for new signals. When a developer opens a Merge Request, GitLab will send a webhook to Jenkins. Jenkins will then, in a fully automated capacity:

1.  **Receive the signal** from GitLab.
2.  **Provision a sterile, consistent build environment** (our `general-purpose-agent`).
3.  **Run the standardized "assembly line"** that we will define in a `Jenkinsfile`.
4.  **Report the `SUCCESS` or `FAILURE`** of that assembly line directly back to the GitLab Merge Request.

This single integration solves all our manual-build problems. It guarantees that every single commit is built and tested in the *exact same way*, every single time. It provides a full, auditable log for every build, and it scales far beyond what any single developer could manage. It's the engine that will power our entire CI/CD stack.

# Chapter 2: The "What" - Our "Controller/Agent" Architecture

Before we can deploy Jenkins, we have to decide on its architecture. A default Jenkins installation is a single, monolithic application that does everything: it serves the UI, manages plugins, *and* runs builds all on the same machine. This is simple, but it's a fragile and insecure design that doesn't scale.

This monolithic model leads to several immediate problems:
* **Toolchain Conflicts:** What if "Project A" needs Java 11 but "Project B" needs Java 17? You end up polluting the controller's filesystem with conflicting dependencies.
* **Security:** A build script that runs on the controller has access to the controller's entire environment, including its credentials and the Docker socket. A rogue script could be disastrous.
* **Performance:** A heavy build (like compiling C++) can consume all the controller's CPU and RAM, making the UI slow or unresponsive for all other users.

We will build a modern, container-based architecture that solves all these problems. Our solution is built on two core concepts: "Pipeline-as-Code" and "Configuration-as-Code."

## 2.1. The "First Principle": Pipeline-as-Code (`Jenkinsfile`)

The first part of our solution is deciding where the "assembly line" instructions live. The build logic (checkout, compile, test, etc.) must be version-controlled *with* the code it's meant to build.

We will accomplish this using a **`Jenkinsfile`**.

This is a plain text file, named `Jenkinsfile`, that lives in the root of our `http-client` repository. It defines every stage of our pipeline directly in a Groovy-based syntax. This is a fundamental shift in responsibility:

* **Jenkins (the Controller)** no longer *defines* the build. It only *executes* the build.
* **The Project (the Code)** is now responsible for telling Jenkins *how* it should be built.

This approach means our build process is now versioned, auditable, and can be reviewed in a Merge Request just like any other piece of code.

## 2.2. The "Second Principle": Configuration-as-Code (JCasC)

The `Jenkinsfile` defines the build process for *a project*, but what about the configuration of the *Jenkins controller itself*? We still need to install plugins, set up security, define our API tokens, and configure our build agents.

If we did this manually through the UI, we would create a **"Snowflake Server"**—a fragile, unique instance that is impossible to replicate and has no audit trail.

Our solution is **Configuration-as-Code (JCasC)**. Just as the `Jenkinsfile` defines the pipeline, a `jenkins.yaml` file will define the *entire configuration of the controller*. This YAML file will be our single source of truth for:
* Creating our `admin` user and setting its password.
* Defining our security matrix (who can do what).
* Installing all our plugins (GitLab, Docker, etc.).
* Connecting to our GitLab server.
* Defining our API credentials.
* Configuring our "cloud" of build agents.

By managing our controller's setup in this file, we make our Jenkins instance 100% reproducible, version-controlled, and auditable.

## 2.3. Our Architecture: The "Foreman and the Ephemeral Worker"

With these two "as-Code" principles, we can now define our final architecture. We will build two separate, specialized Docker images:

1.  **The Controller (Our "Foreman"):** This is our `jenkins-controller` image. Its *only* job is to serve the UI, manage the API, and orchestrate jobs. We will configure it with **zero executors**, meaning it will *never* run a build on its own. It is the "brain" of the operation.
2.  **The Agent (Our "Ephemeral Worker"):** This is our `general-purpose-agent` image. This container is our disposable, "polyglot" toolset, pre-loaded with our entire C++, Rust, and Python toolchain.

This "Foreman/Worker" model is the core of our solution. When a build is triggered, the Controller (Foreman) will "hire" an Agent (Worker) for that one specific job.

## 2.4. The "Mechanism": The Docker Plugin

This "hiring" process is not magic; it's a specific plugin we will configure in our `jenkins.yaml`: the **Docker Plugin**.

This plugin is the "hiring department" for our factory. Here is how it will work:
1.  A developer opens a Merge Request in GitLab.
2.  GitLab sends a webhook to our "Foreman" (the Jenkins Controller).
3.  The Foreman sees the build request and consults its `jenkins.yaml` configuration.
4.  It instructs the **Docker Plugin** to provision a new agent.
5.  The Docker Plugin, using its Docker-out-of-Docker (DooD) capability, connects to the host's `docker.sock` and issues a command:
    `docker run --network cicd-net general-purpose-agent:latest ...`
6.  This new "Worker" container starts, connects to the "Foreman" via our `cicd-net`, and runs the pipeline defined in the `Jenkinsfile`.
7.  After the build is done, the Worker reports `SUCCESS` and is **immediately and automatically destroyed**.

This architecture is the perfect solution. It's scalable, secure (builds are isolated from the controller), and provides a clean, consistent environment for every single build.

# Chapter 3: Architecture Deep Dive: Solving the Java & Docker Puzzles

Deploying Jenkins into our secure, container-based ecosystem presents a unique set of technical hurdles. It's not as simple as our GitLab deployment. This is because Jenkins is a Java application and has its own specific, and sometimes rigid, ways of handling security and networking.

We're about to solve four distinct challenges:
1.  Securing the Jenkins UI (which can't read our `.pem` files).
2.  Granting the Jenkins Controller secure access to the Docker socket (DooD).
3.  Making the Jenkins Controller's JVM trust our internal GitLab server.
4.  Making the Jenkins Agent's environment trust our GitLab server.

Let's tackle them one by one.

---
## 3.1. Puzzle #1: The Controller's HTTPS Keystore (`.p12`)

Our first challenge is that we can't secure the Jenkins UI the same way we secured GitLab.

With GitLab, we simply mounted our `gitlab.cicd.local.crt.pem` and `gitlab.cicd.local.key.pem` files and told its Nginx web server to use them. This worked because Nginx is a C-based application that natively reads `.pem` files.

Jenkins, however, is a Java application. Its web server (Jetty) does not natively read separate `.pem` certificate and key files. Instead, the Java ecosystem prefers a single, password-protected database file called a **Java Keystore (`.jks` or `.p12`)**.

To secure our Jenkins UI at `https://jenkins.cicd.local:10400`, we must convert our "passport" (`.pem` certificate) and its "key" (`.key` file) from Article 2 into this single `.p12` file that Java understands.

Our solution will be to use the `openssl pkcs12 -export` command. This command will bundle our certificate and private key together into a new, password-protected file named `jenkins.p12`. We will then tell Jenkins to use this file to serve HTTPS by passing its path and password in the `JENKINS_OPTS` environment variable when we run the container.

## 3.2. Puzzle #2: The "Build-Time" DooD Fix (Controller)

Our "Foreman" (the Jenkins Controller) needs the ability to "hire" workers. In our architecture, this means it must be able to run Docker commands to spawn our `general-purpose-agent` containers. This requires a Docker-out-of-Docker (DooD) setup.

The obvious first step is to mount the host's Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`. However, this alone will fail.

This creates an immediate and critical permissions challenge, the same one we solved back in Article 1. The `docker.sock` file on the host machine is a protected resource. It's owned by `root` and accessible only by members of the `docker` group. This group has a specific Group ID (GID) on the host, for example, `998`.

Inside our container, the `jenkins` user runs with its own GID (e.g., `1000`). When the `jenkins` user tries to access the mounted socket, the host's kernel sees a request from GID `1000`, compares it to the socket's required GID `998`, and denies access.

We will solve this not at runtime, but at *build time*. This is a cleaner, more permanent solution.
1.  Our `02-build-images.sh` script will first inspect the host and find the numerical GID of its `docker` group.
2.  It will pass this number into the `docker build` command using the `--build-arg HOST_DOCKER_GID` flag.
3.  Inside our `Dockerfile.controller`, we will receive this argument. We will then execute a `RUN` command that:
    * Installs the `docker-ce-cli` package.
    * Creates a new `docker` group *inside the container*.
    * Crucially, it uses the `HOST_DOCKER_GID` to **set the new group's GID to the exact same number as the host**.
    * Finally, it adds the `jenkins` user to this newly created, correctly-ID'd group.

By baking this permission into the image itself, we create a controller that is *born* with the correct permissions. This makes our deployment script much cleaner, as we no longer need to use runtime flags like `--group-add` to modify the user's identity.

## 3.3. Puzzle #3: The "Baked-in" JVM Trust (Controller)

This is one of the most significant challenges in the entire stack. Even with our DooD permissions fixed, our controller will still fail.

The moment our `gitlab-branch-source` plugin (which we'll configure in JCasC) tries to scan our repository at `https://gitlab.cicd.local`, the build will fail with a `javax.net.ssl.SSLHandshakeException`.

The reason for this is that the **Java Virtual Machine (JVM) maintains its own, isolated trust store**.

When we built our controller image, we fixed the *operating system's* trust store by running `update-ca-certificates`. This is great for OS-level tools like `git` or `curl`. However, the Jenkins controller is a Java application. The JVM *completely ignores* the OS trust store and only trusts the certificates found inside its own `cacerts` file (a Java-specific keystore).

Our internal CA is not in that file, so from the JVM's perspective, our `gitlab.cicd.local` certificate is untrusted, and it will refuse all SSL connections.

Our solution is to "bake" our CA's trust directly into the controller's JVM. During our `Dockerfile.controller` build, right after we `COPY` our `ca.pem` file, we will add a `RUN` command. This command will use the Java `keytool` utility—the standard tool for managing Java keystores—to import our `ca.pem` directly into the JVM's master `cacerts` file.

This permanently solves the problem. Our custom `jenkins-controller` image will now be born with a JVM that implicitly trusts every certificate (like GitLab's) that our internal CA has signed. This will allow all Java-based plugins to make secure HTTPS connections to our other internal services without any errors.

## 3.4. Puzzle #4: The Agent's "Dual Trust"

Finally, we must solve the trust problem for our ephemeral agents. It's a common oversight to assume that because the controller trusts GitLab, the agents will too. But the agent is a completely separate container, with its own filesystem, its own OS, and its own trust stores.

When our pipeline kicks off, the *agent* is the container that actually runs the `git clone` command against `https://gitlab.cicd.local`. If the agent doesn't trust our CA, the clone will immediately fail with an SSL verification error.

This reveals a new, more complex challenge: the agent has a "dual trust" requirement. It needs to trust our internal CA in **two different places** to satisfy our "polyglot" toolchain:

1.  **OS-Level Trust (for `git`):** The `git` command is a standard Linux application. It relies on the operating system's trust store (the certificates in `/usr/local/share/ca-certificates/`) to validate the SSL connection.
2.  **JVM-Level Trust (for `sonar-scanner`):** Our pipeline will *also* run Java-based tools. The most important one for our stack will be the `sonar-scanner` CLI (for our future SonarQube article). Just like the Jenkins controller, this is a Java tool that *completely ignores* the OS trust store and relies *only* on its own `cacerts` file.

A failure in either store will break our pipeline. The `git clone` would fail, or the quality scan would fail.

Therefore, our `Dockerfile.agent` must solve *both* problems simultaneously. We will add a build step that:
1.  `COPY`-ies our `ca.pem` file into the build context.
2.  Runs `update-ca-certificates` to add the CA to the OS trust store. This fixes `git`.
3.  Runs the Java `keytool -importcert` command to add the *same* CA to the JVM's `cacerts` file. This fixes `sonar-scanner` and any other Java-based tools.

By baking in this "dual trust," our `general-purpose-agent` will be born ready to communicate securely with all other services in our stack, regardless of the tool being used.

# Chapter 4: Action Plan (Part 1) – The "Blueprints" (Dockerfiles & Plugins)

With our architecture defined and our key integration challenges solved, we can now start building our two Docker images. We'll start by defining the "blueprints" for our controller and agent.

The first step is to create the "shopping list" of plugins our controller will need. This file, `plugins.txt`, will be fed to the Jenkins plugin installer during our image build, ensuring our controller is born with all the "office furniture" it needs to do its job.

---
## 4.1. The "Plugin List" (`plugins.txt`)

This file is a simple list of plugin IDs and their versions (we'll use `latest` for simplicity). Each one adds a critical piece of functionality that enables our specific architecture.

Here are the key plugins we're installing and what they do:

* **`configuration-as-code`:** This is the core of our "Configuration-as-Code" (JCasC) strategy. It's the plugin that will read our `jenkins.yaml` file on boot and configure the entire Jenkins instance, from security realms to API tokens.
* **`matrix-auth`:** This is the "security guard" plugin. It provides the granular, grid-based permission system (`globalMatrix`) that our `jenkins.yaml` file will configure. This is what allows us to lock down anonymous users while granting full rights to our `admin` user.
* **`gitlab-branch-source`:** This is the modern, official "bridge" to GitLab. It provides two essential features:
    1.  The **"Multibranch Pipeline"** job type, which can scan a GitLab project and build all its branches.
    2.  The webhook endpoint (`/gitlab-webhook/trigger`) that allows GitLab to notify Jenkins of new commits and merge requests instantly.
* **`docker-plugin`:** This is our "hiring department." It's the plugin that allows the controller to connect to the Docker socket, interpret our "cloud" configuration from `jenkins.yaml`, and physically spawn our `general-purpose-agent` containers.
* **`pipeline-model-definition`:** This is a crucial dependency. We discovered during our earlier research that the `docker-plugin` will not load correctly without it. It provides the core APIs for defining declarative pipelines, which our agent-based model relies on.

## 4.2. The "Foreman's Office" (`Dockerfile.controller`)

With our plugin list defined, we can now write the blueprint for our "Foreman" or `jenkins-controller`. This `Dockerfile` is a surgical script designed to solve our specific architectural challenges *at build time*, resulting in a clean, secure, and ready-to-run image.

We'll start by using the official `jenkins/jenkins:lts-jdk21` image as our base. This provides a trusted, stable foundation with a recent Java version.

From there, the first thing we do is define the `HOST_DOCKER_GID` build argument. This allows us to pass in the host's Docker group ID during the build process. We then immediately switch to `USER root` because we need to perform two critical system-level installations.

The first installation is for Docker-out-of-Docker (DooD). This is a single, multi-step `RUN` command that:
1.  Adds the official Docker APT repository.
2.  Installs the `docker-ce-cli` package.
3.  **Fixes the GID mismatch.** This is the key. It inspects the `HOST_DOCKER_GID` we passed in. It then creates a `docker` group *inside the container* with that exact numerical GID and adds the `jenkins` user to it. This is a permanent, clean solution. By solving the permission issue at the image level, we don't have to use any special `--group-add` flags in our `docker run` command, making our deployment script much simpler.

The second installation solves our Java trust challenge. This `RUN` command `COPY`-ies our `ca.pem` (from Article 2) into the container and immediately uses the Java `keytool` utility to import it into the master `cacerts` trust store. This "bakes" our internal CA's trust directly into the controller's JVM, permanently eliminating any `SSLHandshakeException` errors when Jenkins tries to contact our GitLab server.

With these system-level fixes applied, we switch back to the low-privilege `USER jenkins`.

Finally, as the `jenkins` user, we `COPY` our `plugins.txt` file and run the `jenkins-plugin-cli` script. This will read our list and install every plugin, ensuring our controller boots up for the first time with all the tools (JCasC, Docker, GitLab) it needs to execute our plan.

## 4.3. The "Factory Worker" (`Dockerfile.agent`)

This is the blueprint for our `general-purpose-agent`, our "polyglot" factory worker. This image is the real workhorse of our pipeline. Its entire purpose is to be a self-contained, pre-loaded toolset, ready to build our complex "hero project" with zero setup.

We start `FROM jenkins/agent:latest-jdk21`. This is a crucial starting point. Unlike the `jenkins/jenkins` controller image, this one is a bare-bones Debian base that includes the Java JDK and the `agent.jar` file, which is responsible for communicating with the controller.

As we did with the controller, we immediately switch to `USER root` to begin our system-level installations.

First, we install all the OS dependencies. This `RUN apt-get install...` command is a "harvested" and expanded version of the one from our `dev-container`. It includes everything our hero project needs: `cmake`, `build-essential`, `libboost-all-dev`, `libcurl4-openssl-dev`, and all the Python build dependencies.

Next, we run the same custom build commands from our `dev-container` to compile and install our specific versions of **GCC** and the **Python** runtimes. This ensures our build agent has the *exact same toolchain* as our development environment, which is the key to solving the "it works on my machine" problem.

We also add a new step to install the `sonar-scanner` CLI by downloading it from SonarSource, unzipping it, and adding it to the system's `PATH`.

With the toolchain installed, we tackle the "dual trust" challenge. We add a `RUN` command that `COPY`-ies our `ca.pem` and then:
1.  Runs `update-ca-certificates`. This makes the OS (and tools like `git`) trust our internal CA.
2.  Runs `keytool -importcert...`. This makes the agent's *own JVM* (and tools like `sonar-scanner`) trust our internal CA.

This is where we hit a critical discovery from our debugging. The next `USER` command is vital. We switch to `USER jenkins` *before* installing our user-space tools. If we hadn't, `rustup` would have installed everything in `/root/.cargo`, which the `jenkins` user can't access.

So, as the `jenkins` user, we `RUN` the `rustup` and `juliaup` installers. This correctly places their binaries in `/home/jenkins/.cargo/bin` and `/home/jenkins/.juliaup/bin`. We follow this with an `ENV PATH` instruction to permanently add these new directories to the `jenkins` user's `PATH`.

Finally, we address the most significant challenge we found during testing. Our `docker image inspect` revealed that the base `jenkins/agent` image has **no `ENTRYPOINT`**. This is why our builds were failing with the `exec: "-url": executable file not found` error. The Docker plugin was passing the JNLP connection arguments as a `CMD`, but there was no entrypoint program to receive them.

We solve this by adding the final, critical instruction to our Dockerfile:
`ENTRYPOINT ["java", "-jar", "/usr/share/jenkins/agent.jar"]`

This "promotes" our image from a simple "bag of tools" to a fully functional, executable agent. This `ENTRYPOINT` is the Java program that will run, consume the `-url`, `-secret`, and `-name` arguments, and successfully connect back to our Jenkins controller.

# Chapter 5: Action Plan (Part 2) – The "Factory Layout" (JCasC)

With our two "blueprints" (`Dockerfile.controller` and `Dockerfile.agent`) designed, we now need to write the "master plan" that tells the Jenkins controller how to operate. This is our Configuration-as-Code (JCasC) file, `jenkins.yaml`.

This file is the "factory layout" for our "Foreman's office." It defines everything: where the doors are, who has keys, what tools are in the cabinets, and how to contact the "hiring department."

We won't write this file by hand. Instead, our `01-setup-jenkins.sh` script will *generate* it. This allows us to programmatically inject values like our port numbers and use environment variables for our secrets. This approach gives us the best of both worlds: a clean, version-controlled YAML structure and a secure way to handle sensitive passwords and tokens.

Let's deconstruct the `jenkins.yaml` file that our setup script will create.

-----

## 5.1. The `jenkins.yaml` File

### The `jenkins:` Block: Core Configuration

This is the main block for the controller itself.

```yaml
jenkins:
  systemMessage: "Jenkins Controller - CI/CD Stack - ${HOSTNAME}"
  numExecutors: 0
  slaveAgentPort: 10401
  securityRealm:
    local:
      allowsSignup: false
      users:
        - id: "admin"
          password: "${JENKINS_ADMIN_PASSWORD}"
  authorizationStrategy:
    globalMatrix:
      entries:
        - user:
            name: "admin"
            permissions:
              - "Overall/Administer"
        # ... (other permissions) ...
```

Here's what we're defining:

* **`numExecutors: 0`**: This is the most important setting for our architecture. We are explicitly telling the "Foreman" (Controller) that it is **not allowed to run any builds itself**. Its executor count is zero. This enforces our "Controller/Agent" model, ensuring all work is delegated to ephemeral agents.
* **`slaveAgentPort: 10401`**: This defines the internal port our agents will use to connect back to the controller (via the JNLP protocol). We define this here in JCasC, which is the modern, correct way to set it. We'll then expose this port in our `docker run` command.
* **`securityRealm:`**: This block creates our users. We define a local `admin` user and set its password by reading from the `${JENKINS_ADMIN_PASSWORD}` environment variable. This variable will be passed into the container from our `jenkins.env` file.
* **`authorizationStrategy:`**: This is where our `matrix-auth` plugin comes in. We use `globalMatrix` to grant our `admin` user full `Overall/Administer` permissions. This locks down the instance so that only our `admin` user can do anything, securing Jenkins from the moment it boots.

### The `credentials:` Block: The "Key Cabinet"

This block is at the **root level** (not nested under `jenkins:`). This is one of those syntax details we discovered through debugging. This block defines all the secret tokens our Jenkins system needs.

```yaml
credentials:
  system:
    domainCredentials:
      - credentials:
          - string:
              id: "gitlab-api-token"
              scope: GLOBAL
              description: "GitLab API Token for Jenkins"
              secret: "${GITLAB_API_TOKEN}"
          - usernamePassword:
              id: "gitlab-checkout-credentials"
              scope: GLOBAL
              description: "GitLab Project Token for repo checkout"
              username: "gitlab-checkout-bot"
              password: "${GITLAB_CHECKOUT_TOKEN}"
```

Here, we are creating two critical credentials:

1.  **`gitlab-api-token`**: This is a `string` (or secret text) credential. It holds our "all-powerful" GitLab PAT. The controller itself will use this token for API calls, like scanning repositories or reporting build status.
2.  **`gitlab-checkout-credentials`**: This is a `usernamePassword` credential. It holds the *Project Access Token* we created for our `http-client` project. The `username` is just a descriptive label, and the `password` is the token itself (read from `${GITLAB_CHECKOUT_TOKEN}`). Our pipeline job will use this to `git clone` the private repository.

### The `unclassified:` Block: The "GitLab Bridge"

This is another root-level block, and its name is not obvious. `unclassified` is the JCasC key for plugins that don't have their own, cleaner top-level key. Here, we configure the `gitlab-branch-source` plugin.

```yaml
unclassified:
  gitLabServers:
    servers:
      - name: "Local GitLab"
        serverUrl: "https://gitlab.cicd.local:10300"
        credentialsId: "gitlab-api-token"
        manageWebHooks: true
```

This configuration tells Jenkins:

* There is one GitLab server, and its name is "Local GitLab".
* Its URL is `https://gitlab.cicd.local:10300`.
* To authenticate against its API, it should use the `gitlab-api-token` credential we just defined.
* `manageWebHooks: true`: This is a powerful setting. It gives Jenkins permission to *automatically* create webhooks in our GitLab projects for us.

### The `clouds:` Block: The "Hiring Department"

This final root-level block is the most complex and important. It's where we configure the `docker-plugin` and define our entire "Foreman/Worker" dynamic.

```yaml
clouds:
  - docker:
      name: "docker-local"
      dockerApi:
        dockerHost:
          uri: "unix:///var/run/docker.sock"
      templates:
        - name: "general-purpose-agent"
          labelString: "general-purpose-agent"
          remoteFs: "/home/jenkins/agent"
          pullStrategy: 'PULL_NEVER'
          dockerCommand: ""
          removeVolumes: true
          dockerTemplateBase:
            image: "general-purpose-agent:latest"
            network: "cicd-net"
          connector:
            jnlp:
              jenkinsUrl: "https://jenkins.cicd.local:10400/"
```

Let's deconstruct this:

* **`dockerApi:`**: We point the plugin to the DooD socket at `unix:///var/run/docker.sock`.
* **`templates:`**: This is the list of "worker types" our Foreman can hire. We define one:
    * **`labelString: "general-purpose-agent"`**: This is the "job title." Our `Jenkinsfile` will request a worker with this label (`agent { label 'general-purpose-agent' }`).
    * **`pullStrategy: 'PULL_NEVER'`**: This was a key discovery. It tells Jenkins to *never* try to pull the image from Docker Hub and to *only* use the local `general-purpose-agent:latest` image we built.
    * **`dockerCommand: ""`**: This was our *other* major debugging fix. It tells the plugin to *not* override the container's `ENTRYPOINT`, which is what finally solved our `exec: "-url": executable file not found` error.
    * **`removeVolumes: true`**: This is a cleanup fix. It tells Jenkins to delete the agent's anonymous volumes when the container is removed, preventing our host from filling up with orphaned volumes.
    * **`dockerTemplateBase:`**: This defines the agent's runtime.
        * **`image: "general-purpose-agent:latest"`**: The name of our custom-built image.
        * **`network: "cicd-net"`**: This is critical. It connects our agent to our private "city" network, allowing it to resolve `gitlab.cicd.local`.
    * **`connector:`**: This tells the agent *how* to find the Foreman. We give it the full JNLP URL: `https://jenkins.cicd.local:10400/`.