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

-----

## 4.1. The "Plugin List" (`plugins.txt`)

This file is a simple list of plugin IDs and their versions (we'll use `latest` for simplicity). Each one adds a critical piece of functionality that enables our specific architecture.

Here is the complete `plugins.txt` file.

```text
#
# -----------------------------------------------------------
#                      plugins.txt
#
# This file lists all plugins to be installed by the
# 'jenkins-plugin-cli' during our image build.
#
# Each plugin is a piece of "office furniture" for our
# "Foreman," giving it new capabilities.
# -----------------------------------------------------------

# --- Dependencies and standard plugins ---
pipeline-model-definition:latest
cloudbees-folder:latest
antisamy-markup-formatter:latest
build-timeout:latest
credentials-binding:latest
timestamper:latest
ws-cleanup:latest
ant:latest
gradle:latest
workflow-aggregator:latest
github-branch-source:latest
pipeline-github-lib:latest
pipeline-graph-analysis:latest
git:latest
ssh-slaves:latest
ldap:latest
email-ext:latest
mailer:latest
dark-theme:latest

# --- Core Setup & Configuration ---

# The "Blueprint Reader": Allows us to configure Jenkins using
# our 'jenkins.yaml' file. The core of JCasC.
configuration-as-code:latest

# The "Security Guard": Allows us to create the granular
# "who-can-do-what" permissions matrix.
matrix-auth:latest

# --- CI/CD Integration Plugins ---

# The "Red Phone": The bridge to GitLab. This plugin
# allows Jenkins to receive webhooks from GitLab and
# provides the "Multibranch Pipeline" job type.
gitlab-branch-source:latest

# The "Hiring Department": This is the Docker Cloud plugin.
# It's what allows our controller to "spawn" our
# 'general-purpose-agent' containers.
docker-plugin:latest

# The "Secure Warehouse" Connector: Provides the native
# 'rtUpload' steps to publish our artifacts to Artifactory.
artifactory:latest

# The "Quality Inspector" Connector: Provides the
# 'withSonarQubeEnv' and 'waitForQualityGate' steps.
sonar:latest
```

### Deconstructing `plugins.txt`

Here are the key plugins we're installing and what they do:

* **`configuration-as-code`:** This is the core of our "Configuration-as-Code" (JCasC) strategy. It's the plugin that will read our `jenkins.yaml` file on boot and configure the entire Jenkins instance, from security realms to API tokens.
* **`matrix-auth`:** This is the "security guard" plugin. It provides the granular, grid-based permission system (`globalMatrix`) that our `jenkins.yaml` file will configure. This is what allows us to lock down anonymous users while granting full rights to our `admin` user.
* **`gitlab-branch-source`:** This is the modern, official "bridge" to GitLab. It provides two essential features:
    1.  The **"Multibranch Pipeline"** job type, which can scan a GitLab project and build all its branches.
    2.  The webhook endpoint (`/gitlab-webhook/trigger`) that allows GitLab to notify Jenkins of new commits and merge requests instantly.
* **`docker-plugin`:** This is our "hiring department." It's the plugin that allows the controller to connect to the Docker socket, interpret our "cloud" configuration from `jenkins.yaml`, and physically spawn our `general-purpose-agent` containers.
* **`pipeline-model-definition`:** This is a crucial dependency we discovered during our research. The `docker-plugin` will not load correctly without it, as it provides the core APIs for defining the declarative pipelines that our agent-based model relies on.

## 4.2. The "Foreman's Office" (`Dockerfile.controller`)

With our plugin list defined, we can now write the blueprint for our "Foreman" or `jenkins-controller`. This `Dockerfile` is a surgical script designed to solve our specific architectural challenges *at build time*, resulting in a clean, secure, and ready-to-run image.

Here is the complete `Dockerfile.controller`:

```dockerfile
#
# -----------------------------------------------------------
#               Dockerfile.controller
#
#  This blueprint builds our "Foreman" (Jenkins Controller).
#
#  1. DooD: Installs Docker CLI & fixes GID permissions.
#  2. CA Trust: Bakes in our Local CA to the JVM trust store.
#  3. Plugins: Installs all plugins from 'plugins.txt'.
#
# -----------------------------------------------------------

# 1. Start from the official Jenkins Long-Term Support image
FROM jenkins/jenkins:lts-jdk21
LABEL authors="warren_jitsing"

# 2. Accept the host's 'docker' GID as a build-time argument
ARG HOST_DOCKER_GID

# 3. Switch to 'root' to install software and fix permissions
USER root

# 4. Copy our Local CA cert from the build context
# (Our '01-setup-jenkins.sh' will place this file here)
COPY ca.pem /tmp/ca.pem

# 5. Fix CA Trust (for both OS/git and JVM)
# This is "baked in" for simplicity and robustness
RUN cp /tmp/ca.pem /usr/local/share/ca-certificates/cicd-stack-ca.crt \
    && update-ca-certificates \
    && keytool -importcert \
        -keystore /opt/java/openjdk/lib/security/cacerts \
        -storepass changeit \
        -file /tmp/ca.pem \
        -alias "CICD-Root-CA" \
        -noprompt \
    && rm /tmp/ca.pem

# 6. Install Docker CLI & Fix GID Mismatch
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends \
        docker-ce-cli \
    && groupadd --gid $HOST_DOCKER_GID docker \
    && usermod -aG docker jenkins \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 7. Switch back to the unprivileged 'jenkins' user
USER jenkins

# 8. Copy our plugin list into the official ref directory
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt

# 9. Run the official plugin installer script
RUN jenkins-plugin-cli -f /usr/share/jenkins/ref/plugins.txt
```

-----

### Deconstructing `Dockerfile.controller`

Let's walk through this blueprint layer by layer to understand how it solves our specific challenges.

* **`FROM jenkins/jenkins:lts-jdk21`**
  We start with the official Long-Term Support (LTS) image for the Jenkins controller. This provides a trusted, stable foundation with a recent Java version.

* **`ARG HOST_DOCKER_GID`**
  This instruction defines a build-time argument. It's how we'll pass the host's Docker group ID into the image when we run our `02-build-images.sh` script.

* **`USER root`**
  We switch to the `root` user because we need to perform two critical, system-level installations that the standard `jenkins` user doesn't have permission to do.

* **Step 5: Fix CA Trust**
  This `RUN` command solves our **"JVM Trust" puzzle**. It `COPY`-ies the `ca.pem` we staged in our setup script and:

    1.  Runs `update-ca-certificates` to add our CA to the **Operating System's** trust store.
    2.  Runs the Java `keytool` command to import the *same certificate* into the **JVM's** master `cacerts` file.
        By "baking" this trust into the image, we permanently solve any `SSLHandshakeException` errors. Our controller is now born with a JVM that implicitly trusts our internal GitLab server.

* **Step 6: Install Docker CLI & Fix GID Mismatch**
  This `RUN` command solves our **"DooD Permission" puzzle**. It's a single, multi-step command that:

    1.  Adds the official Docker APT repository.
    2.  Installs the `docker-ce-cli` package, giving our controller the `docker` command.
    3.  **Fixes the GID.** This is the key. It executes `groupadd --gid $HOST_DOCKER_GID docker` to create a new `docker` group *inside the container* that has the *exact same numerical GID* as the one on our host.
    4.  Finally, it adds the `jenkins` user to this new, correctly-ID'd group.
        This is a permanent, clean solution. By solving the permission issue at the image level, we don't have to use any special `--group-add` flags in our `docker run` command.

* **`USER jenkins`**
  With all our system-level modifications complete, we switch back to the low-privilege `jenkins` user for the rest of the build.

* **Steps 8 & 9: Install Plugins**
  This is the final step. We `COPY` our `plugins.txt` "shopping list" into the official location Jenkins uses for pre-installing plugins. We then `RUN` the `jenkins-plugin-cli` script, which reads this list and installs every plugin. This ensures our controller boots up for the first time with all the tools (JCasC, Docker, GitLab) it needs.

## 4.3. The "Factory Worker" (`Dockerfile.agent`)

This is the blueprint for our `general-purpose-agent`, our "polyglot" factory worker. This image is the real workhorse of our pipeline. Its entire purpose is to be a self-contained, pre-loaded toolset, ready to build our complex "hero project" with zero setup.

We start `FROM jenkins/agent:latest-jdk21`. This is a crucial starting point. Unlike the `jenkins/jenkins` controller image, this one is a bare-bones Debian base that includes the Java JDK and the `agent.jar` file, which is responsible for communicating with the controller.

Here is the complete `Dockerfile.agent`:

```dockerfile
#
# -----------------------------------------------------------
#                    Dockerfile.agent
#
#  This blueprint builds our "General Purpose Worker".
#  It starts from the base Jenkins agent image and "harvests"
#  all the complex toolchains from our dev-container to
#  create a "polyglot" builder.
#
#  It is a "cattle" image: stateless, disposable, but
#  loaded with all the tools our "hero project" needs.
# -----------------------------------------------------------

# 1. Start from the official Jenkins agent image (Debian 12 + JDK 21)
FROM jenkins/agent:latest-jdk21
LABEL authors="warren_jitsing"

# 2. Get ARGs from our dev-container for custom builds
ARG py312="3.12.12"
ARG py313="3.13.9"
ARG py314="3.14.0"
ARG gcc15="15.2.0"

# 3. Switch to 'root' to install everything
USER root

# 4. Copy our Local CA cert from the build context
# (Our '01-setup-jenkins.sh' will place this file here)
COPY ca.pem /tmp/ca.pem

# 5. Install all OS dependencies (harvested from dev-container + hero project)
# This includes base tools, "hero project" deps, and Python build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl flex \
    git git-lfs gnupg2 sudo wget unzip \
    llvm lcov hyperfine libcurl4-openssl-dev libboost-all-dev \
    libbz2-dev libffi-dev libgdbm-compat-dev libgdbm-dev liblzma-dev \
    libncurses5-dev libreadline-dev libsqlite3-dev libssl-dev \
    python3-dev python3-pip python3-tk uuid-dev zlib1g-dev \
    m4 patch pkg-config procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 6. Build and install custom GCC
RUN mkdir -p /tmp/deps/gcc \
    && cd /tmp/deps/gcc \
    && curl -fsSL "https://github.com/gcc-mirror/gcc/archive/refs/tags/releases/gcc-${gcc15}.tar.gz" | tar -xz --strip-components=1 \
    && ./contrib/download_prerequisites \
    && mkdir build && cd build \
    && ../configure --disable-multilib --enable-languages=c,c++ \
    && make -j $(nproc) \
    && make install \
    && cd / \
    && rm -rf /tmp/deps

# 7. Add our new custom GCC to the system-wide PATH
RUN echo 'export PATH="/usr/local/bin:${PATH}"' > /etc/profile.d/gcc.sh \
    && echo 'export LD_LIBRARY_PATH="/usr/local/lib64:${LD_LIBRARY_PATH}"' >> /etc/profile.d/gcc.sh

# 8. Build and install custom Python versions
RUN for version in $py312 $py313 $py314; do \
        echo "--- Building Python version ${version} ---"; \
        mkdir -p /tmp/deps/python; \
        cd /tmp/deps/python; \
        curl -fsSL "https://github.com/python/cpython/archive/refs/tags/v${version}.tar.gz" | tar -xz --strip-components=1; \
        CONFIGURE_FLAGS="--enable-optimizations --enable-loadable-sqlite-extensions --with-lto=full"; \
        if [ "$version" = "$py313" ] || [ "$version" = "$py314" ]; then \
            echo "--- Adding --disable-gil flag for nogil build ---"; \
            CONFIGURE_FLAGS="$CONFIGURE_FLAGS --disable-gil"; \
        fi; \
        ./configure $CONFIGURE_FLAGS; \
        make -j $(nproc); \
        make altinstall; \
        cd / ; \
    done \
    && rm -rf /tmp/deps

# 9. Install SonarScanner CLI (as root)
RUN wget -O /tmp/sonar.zip "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-7.3.0.5189-linux-x64.zip" \
    && unzip /tmp/sonar.zip -d /opt \
    && mv /opt/sonar-scanner-* /opt/sonar-scanner \
    && ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/bin/sonar-scanner \
    && rm /tmp/sonar.zip

# 10. Fix CA Trust (for both OS/git and JVM) (as root)
RUN cp /tmp/ca.pem /usr/local/share/ca-certificates/cicd-stack-ca.crt \
    && update-ca-certificates \
    && keytool -importcert \
        -keystore /opt/java/openjdk/lib/security/cacerts \
        -storepass changeit \
        -file /tmp/ca.pem \
        -alias "CICD-Root-CA" \
        -noprompt \
    && rm /tmp/ca.pem

# 11. Switch to the default agent user
USER jenkins

# 12. Install user-specific toolchains (Rust and Julia)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && curl -fsSL https://install.julialang.org | sh -s -- -y

# 13. Install cargo-llvm-cov
# We must source the env file in the *same* command
RUN . "$HOME/.cargo/env" && cargo install cargo-llvm-cov

# 14. Add the new toolchains to the container's PATH
# This ENV instruction makes them available to all subsequent
# Jenkins 'sh' steps.
ENV PATH="/home/jenkins/.cargo/bin:/home/jenkins/.juliaup/bin:${PATH}"

# 15. Set the Entrypoint (must be last)
ENTRYPOINT ["java", "-jar", "/usr/share/jenkins/agent.jar"]
```

-----

### Deconstructing `Dockerfile.agent`

This `Dockerfile` is more complex than the controller's because it's responsible for building our actual "polyglot" toolchain.

* **Steps 1-8: Harvesting the Toolchain**
  Just like our controller, we switch to `root` to install system software. The `apt-get` command is a "harvested" list from our `dev-container`, containing all the C++, Boost, and Python dependencies our "hero project" needs. We then run the *exact same* build-from-source commands for **GCC** and **Python**. This is the key to solving the "it works on my machine" problem: our build agent's toolchain is now identical to our development environment's.

* **Step 9: Pre-installing Future Tools**
  We also take this opportunity to install the `sonar-scanner` CLI. We aren't using it yet, but pre-installing it here means our agent will be ready for our SonarQube (Quality Assurance) article without needing another rebuild.

* **Step 10: The "Dual Trust" Fix**
  This `RUN` command is critical. It solves the trust problem for *both* toolchains on the agent:

    1.  `update-ca-certificates`: This makes the **Operating System** (and thus tools like `git` and `curl`) trust our internal CA.
    2.  `keytool -importcert...`: This makes the **JVM** (and thus Java-based tools like `sonar-scanner`) trust our internal CA.
        Without this "dual fix," either our `git clone` or our future quality scan would fail.

* **Steps 11-14: The User-Context Switch**
  This is the solution to our `cargo: command not found` debugging session. We switch to the `USER jenkins` *before* installing user-space tools. The `rustup` and `juliaup` installers now correctly place their binaries in `/home/jenkins/.cargo/bin`. We then use the `ENV` instruction to permanently add this new directory to the `jenkins` user's `PATH`, making `cargo` and `rustc` available to all pipeline steps.

* **Step 15: The `ENTRYPOINT` Fix**
  This is the final, and most important, instruction. Our investigation with `docker image inspect` revealed that the `jenkins/agent` base image has no `ENTRYPOINT`. This was the cause of our `exec: "-url": executable file not found` error, as the Docker plugin was passing its connection arguments as a command. This line "promotes" our image from a simple "bag of tools" to a functional, executable agent. This Java command is the program that will run, consume the connection arguments, and successfully link our worker to the controller.

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
    * **`dockerCommand: ""`**: This was our *other* major debugging fix. It tells the plugin to *not* override the container's `ENTRYPOINT`, which is what we thought would finally solve our `exec: "-url": executable file not found` error.
    * **`removeVolumes: true`**: This is a cleanup fix. It tells Jenkins to delete the agent's anonymous volumes when the container is removed, preventing our host from filling up with orphaned volumes.
    * **`dockerTemplateBase:`**: This defines the agent's runtime.
        * **`image: "general-purpose-agent:latest"`**: The name of our custom-built image.
        * **`network: "cicd-net"`**: This is critical. It connects our agent to our private "city" network, allowing it to resolve `gitlab.cicd.local`.
    * **`connector:`**: This tells the agent *how* to find the Foreman. We give it the full JNLP URL: `https://jenkins.cicd.local:10400/`.

### A Critical Note on JCasC and Credentials

This `credentials:` block highlights a fundamental, and critical, part of our Configuration-as-Code architecture that we discovered during our testing.

**1. The JCasC File is the Single Source of Truth**

Our `jenkins.yaml` file is the *authoritative* definition of our Jenkins configuration. When the controller starts, the JCasC plugin reads this file and forces the system's configuration to match it.

This means **any credentials you add manually via the UI will be lost** when the container is restarted or re-deployed. We experienced this ourselves: after manually adding our `gitlab-checkout-credentials` in the UI, a simple container restart wiped them out, causing our builds to fail again.

The only way to create *permanent* credentials that survive restarts is to define them here, in our `jenkins.yaml` blueprint.

**2. Understanding GitLab Tokens in JCasC**

In our file, we are using two *different* credential *kinds* for two different GitLab tokens. This is a deliberate choice for our architecture:

* **`string` (for `gitlab-api-token`):** This is a **Personal Access Token (PAT)** with `api` scope. It's used by the `gitlab-branch-source` plugin itself to scan repositories and report build statuses. The plugin is designed to read a `string` (or "Secret Text") credential.

* **`usernamePassword` (for `gitlab-checkout-credentials`):** This is a **Project Access Token (PAT)** with a much more limited `read_repository` scope. This is the token our pipeline's `git clone` command will use. We use the `usernamePassword` type because it's what the Git checkout step expects.
    * **The `username` is just a label.** GitLab's token auth does not care what is in the `username` field (`gitlab-checkout-bot`). It only cares about the token. We are putting the token in the `password` field, which is what `git` will present to the server.

You can use a Personal, Group, or Project token for the `usernamePassword` credential. Our choice to use a **Project Access Token** here is an example of the **Principle of Least Privilege**: the build pipeline only gets permission to *read this one project*, not our entire GitLab instance.


# Chapter 6: Action Plan (Part 3) – The "Architect, Build, Deploy" Scripts

With our "blueprints" (`Dockerfiles`) and "factory layout" (the `jenkins.yaml` design) complete, it's time to execute our plan. We will use a three-script "Architect, Build, Deploy" pattern, just as we did for our previous services.

This separates our logic cleanly:

1.  **`01-setup-jenkins.sh`**: The "Architect" script that runs on the host to *prepare* all configuration.
2.  **`02-build-images.sh`**: The "Build" script that *creates* our custom Docker images.
3.  **`03-deploy-controller.sh`**: The "Deploy" script that *runs* the Jenkins controller.

Let's start with the "Architect."

## 6.1. The "Architect" Script (`01-setup-jenkins.sh`)

This is our master setup script. Its sole purpose is to run on the host machine and generate *all* the configuration "artifacts" our other scripts and Dockerfiles will need. It's the "blueprint processor" that assembles all our plans and secrets into ready-to-use files.

Here is the complete script.

```bash
#!/usr/bin/env bash

#
# -----------------------------------------------------------
#               01-setup-jenkins.sh
#
#  This is the master "architect" script for Jenkins.
#
#  It runs *once* on the host machine to generate all the
#  "blueprints" (JCasC, etc.) needed to deploy our Controller.
#
#  1. Scoped Env: Creates a 'jenkins.env' file.
#  2. Keystore:   Generates the 'jenkins.p12' Java keystore.
#  3. JCasC:      Writes the 'jenkins.yaml' file with the
#                 correct Docker Cloud syntax.
#  4. CA Trust:   Copies 'ca.pem' into the build context
#     for both Dockerfiles to use.
#
# -----------------------------------------------------------

set -e
echo "🚀 Starting Jenkins 'Architect' Setup..."

# --- 1. Define Core Paths & Variables ---

# This is our main config directory from Article 1
JENKINS_CONFIG_DIR="$HOME/cicd_stack/jenkins/config"

# This is our Jenkins build context (current directory)
BUILD_CONTEXT_DIR=$(pwd)

# Master "Secrets" file from Article 1
MASTER_ENV_FILE="$HOME/cicd_stack/cicd.env"

# Source the master secrets file to load them into this script
if [ ! -f "$MASTER_ENV_FILE" ]; then
    echo "⛔ ERROR: Master env file not found at $MASTER_ENV_FILE"
    exit 1
fi
source "$MASTER_ENV_FILE"

# --- 2. Define Ports & Passwords ---
# We will use the 104xx block for Jenkins
JENKINS_HTTPS_PORT="10400"
JENKINS_JNLP_PORT="10401"

# Generate passwords if they aren't set in the env file
: "${JENKINS_ADMIN_PASSWORD:="admin-$(openssl rand -hex 8)"}"
: "${JENKINS_KEYSTORE_PASSWORD:="key-$(openssl rand -hex 12)"}"

echo "🔧 Jenkins Ports Set:"
echo "   - UI (HTTPS): $JENKINS_HTTPS_PORT"
echo "   - Agent (JNLP): $JENKINS_JNLP_PORT"

# --- 3. Create "Scoped" jenkins.env File ---
# This is our "Least Privilege" secrets file for the container
SCOPED_ENV_FILE="$BUILD_CONTEXT_DIR/jenkins.env"
echo "🔑 Creating scoped 'jenkins.env' file..."
cat << EOF > "$SCOPED_ENV_FILE"
# This file is auto-generated by 01-setup-jenkins.sh
# It contains *only* the secrets needed by Jenkins.

# --- JCasC Variables ---
JENKINS_ADMIN_PASSWORD=${JENKINS_ADMIN_PASSWORD}
GITLAB_API_TOKEN=${GITLAB_API_TOKEN}
GITLAB_CHECKOUT_TOKEN=${GITLAB_CHECKOUT_TOKEN}

# --- Keystore Password ---
JENKINS_KEYSTORE_PASSWORD=${JENKINS_KEYSTORE_PASSWORD}
EOF
grep -qxF "jenkins.env" .gitignore || echo "jenkins.env" >> .gitignore
echo "   Done."

# --- 4. Prepare Certificate Assets ---
echo "🔐 Preparing SSL certificates..."

# Create directories for the Keystore
SSL_DIR="$JENKINS_CONFIG_DIR/ssl"
mkdir -p "$SSL_DIR"

# Define CA and Service Cert paths from Article 2
CA_CERT_PATH="$HOME/cicd_stack/ca/pki/certs/ca.pem"
SERVICE_CERT_PATH="$HOME/cicd_stack/ca/pki/services/jenkins.cicd.local/jenkins.cicd.local.crt.pem"
SERVICE_KEY_PATH="$HOME/cicd_stack/ca/pki/services/jenkins.cicd.local/jenkins.cicd.local.key.pem"
P12_KEYSTORE_PATH="$SSL_DIR/jenkins.p12"

# 4a. Copy 'ca.pem' into our build context for both Dockerfiles
# This will be .gitignore'd
cp "$CA_CERT_PATH" "$BUILD_CONTEXT_DIR/ca.pem"
grep -qxF "ca.pem" .gitignore || echo "ca.pem" >> .gitignore

# 4b. Create the .p12 Java Keystore for the Controller's UI
echo "   Generating 'jenkins.p12' Java Keystore..."
openssl pkcs12 -export \
    -in "$SERVICE_CERT_PATH" \
    -inkey "$SERVICE_KEY_PATH" \
    -name jenkins \
    -out "$P12_KEYSTORE_PATH" \
    -passout "pass:${JENKINS_KEYSTORE_PASSWORD}"
echo "   Done."


# --- 5. Generate JCasC 'jenkins.yaml' ---
JCAS_FILE="$JENKINS_CONFIG_DIR/jenkins.yaml"
echo "📝 Generating 'jenkins.yaml' (JCasC) blueprint..."
cat << EOF > "$JCAS_FILE"
#
# This file is auto-generated by 01-setup-jenkins.sh
# It is the "factory layout" (JCasC) for our Jenkins Controller.
#
jenkins:
  # Set the system message
  systemMessage: "Jenkins Controller - CI/CD Stack - ${HOSTNAME}"

  # This is the fix for the "built-in node" security warning
  numExecutors: 0

  # Configure our JNLP agent port
  slaveAgentPort: ${JENKINS_JNLP_PORT}

  # --- Security Configuration ---
  # Use the modern, nested 'entries' syntax
  authorizationStrategy:
    globalMatrix:
      entries:
        # Grant 'admin' full administrator permissions
        - user:
            name: "admin"
            permissions:
              - "Overall/Administer"
              - "Overall/Read"
              - "Agent/Build"
              - "Agent/Configure"
              - "Agent/Connect"
              - "Agent/Create"
              - "Agent/Delete"
              - "Agent/Disconnect"
              - "Credentials/Create"
              - "Credentials/Delete"
              - "Credentials/ManageDomains"
              - "Credentials/Update"
              - "Credentials/View"
              - "Job/Build"
              - "Job/Cancel"
              - "Job/Configure"
              - "Job/Create"
              - "Job/Delete"
              - "Job/Discover"
              - "Job/Move"
              - "Job/Read"
              - "Job/Workspace"
              - "Run/Delete"
              - "Run/Replay"
              - "Run/Update"
              - "View/Configure"
              - "View/Create"
              - "View/Delete"
              - "View/Read"
        # Grant 'anonymous' read-only access
        - group:
            name: "anonymous"
            permissions:
              - "Overall/Read"
              - "Job/Read"
              - "Job/Discover"
        # Grant 'authenticated' (all logged-in users) basic job rights
        - group:
            name: "authenticated"
            permissions:
              - "Overall/Read"
              - "Job/Read"
              - "Job/Build"
              - "Job/Discover"

  # 'securityRealm' is a child of 'jenkins:'
  securityRealm:
    local:
      allowsSignup: false
      users:
        # Create our 'admin' user with the password from our .env file
        - id: "admin"
          password: "\${JENKINS_ADMIN_PASSWORD}"

  # --- Cloud Configuration (The "Hiring Department") ---
  # 'clouds' is a valid top-level attribute of 'jenkins:'
  clouds:
    - docker:
        name: "docker-local"
        # Point to the DooD socket (permissions fixed in Dockerfile)
        dockerApi:
          dockerHost:
            uri: "unix:///var/run/docker.sock"
        # Define our "General Purpose Worker" template
        templates:
          - name: "general-purpose-agent"
            # This is the correct attribute for the label
            labelString: "general-purpose-agent"
            # The agent's working directory
            remoteFs: "/home/jenkins/agent"
            pullStrategy: 'PULL_NEVER'
            dockerCommand: ""
            removeVolumes: true
            # All base properties are nested inside dockerTemplateBase
            dockerTemplateBase:
              # The custom image we built
              image: "general-purpose-agent:latest"
              # The "road network" for our city
              network: "cicd-net"
            # The connector stays at the top level
            connector:
              jnlp:
                # This 'jenkinsUrl' is for the *agent* to find the controller
                jenkinsUrl: "https://jenkins.cicd.local:${JENKINS_HTTPS_PORT}/"

# --- Tool Configuration ---
# This 'tool' block is at the ROOT level, not inside 'jenkins:'
tool:
  git:
    installations:
      - name: "Default"
        home: "git"

# --- Credentials Configuration ---
credentials:
  system:
    domainCredentials:
      - credentials:
          - string:
              id: "gitlab-api-token"
              scope: GLOBAL
              description: "GitLab API Token for Jenkins"
              secret: "\${GITLAB_API_TOKEN}"
          - usernamePassword:
              id: "gitlab-checkout-credentials"
              scope: GLOBAL
              description: "GitLab Project Token for repo checkout"
              username: "gitlab-checkout-bot"
              password: "\${GITLAB_CHECKOUT_TOKEN}"

# --- Plugin Configuration (The "Bridge" to GitLab) ---
unclassified:
  # The correct JCasC root for 'gitlab-branch-source' is 'gitLabServers'
  gitLabServers:
    servers:
      - name: "Local GitLab"
        serverUrl: "https://gitlab.cicd.local:10300"
        credentialsId: "gitlab-api-token"
        # We don't need 'clientBuilderId' for this plugin,
        # but we do need to enable hook management.
        manageWebHooks: true
        manageSystemHooks: false
EOF
echo "   Done."
echo "✅ Jenkins 'Architect' setup is complete."
echo "   All blueprints (JCasC, env) are generated."
echo "   All certs are staged in the correct locations."
echo "   You can now run '02-build-images.sh'."
```

### Deconstructing the "Architect" Script

This script performs five critical setup tasks before we ever build an image or run a container.

1.  **Sources the Master `cicd.env` File:** It pulls in all our master secrets (like `GITLAB_API_TOKEN`) so it can use them to populate other files.
2.  **Creates a "Scoped" `jenkins.env` File:** This is a key security practice. Instead of passing all our secrets to the controller, this creates a new `jenkins.env` file that contains *only* the secrets Jenkins needs: its admin password, the GitLab API token, the checkout token, and the keystore password. This file is what we'll pass to our container.
3.  **Copies the `ca.pem`:** It copies our CA certificate from Article 2 into the current directory. Our `Dockerfile.controller` and `Dockerfile.agent` will `COPY` this file to "bake in" trust.
4.  **Generates the `.p12` Keystore:** This is the Java SSL solution from Chapter 3. It runs the `openssl pkcs12 -export` command, bundling our `jenkins.cicd.local` certificate and key into the `jenkins.p12` file that the controller's web server can understand.
5.  **Generates the `jenkins.yaml` JCasC File:** This is the script's main job. It writes our entire "factory layout" to `jenkins.yaml`, programmatically inserting our port numbers (`$JENKINS_HTTPS_PORT`) and using the `\${VARIABLE}` syntax to template the secrets. This generated file is the complete, final blueprint for our controller.



## 6.2. The "Build" Script (`02-build-images.sh`)

With our "Architect" script having prepared all the blueprints and staged the `ca.pem` file, we're ready to "build" our images. This script's job is to run the `docker build` commands, feeding our `Dockerfiles` all the build-time arguments they need.

```bash
#!/usr/bin/env bash

#
# -----------------------------------------------------------
#               02-build-images.sh
#
#  This is the "build" script. It builds our two custom
#  Docker images:
#
#  1. jenkins-controller: The "Foreman" (UI)
#  2. general-purpose-agent: The "Worker" (Build Tools)
#
#  It's responsible for finding the host's 'docker' GID
#  and passing all the correct build-time arguments to
#  each Dockerfile.
# -----------------------------------------------------------

set -e
echo "🚀 Starting Jenkins Image Build..."

# --- 1. Find Host Docker GID ---
# We need this for the "build-time" GID fix in Dockerfile.controller
HOST_DOCKER_GID=$(getent group docker | cut -d: -f3)

if [ -z "$HOST_DOCKER_GID" ]; then
    echo "⛔ ERROR: 'docker' group not found on host."
    echo "Please ensure the docker group exists and your user is a member."
    exit 1
fi
echo "🔧 Host 'docker' GID found: $HOST_DOCKER_GID"

# --- 2. Define Toolchain Build Arguments ---
# These ARGs must match what Dockerfile.agent expects
PY312="3.12.12"
PY313="3.13.9"
PY314="3.14.0"
GCC15="15.2.0"

# --- 3. Build the Controller Image ---
echo "--- Building 'jenkins-controller:latest' ---"
docker build --progress=plain \
  --build-arg HOST_DOCKER_GID=$HOST_DOCKER_GID \
  -f Dockerfile.controller \
  -t jenkins-controller:latest .
echo "✅ 'jenkins-controller' build complete."


# --- 4. Build the Agent Image ---
echo "--- Building 'general-purpose-agent:latest' ---"
docker build --progress=plain \
  --build-arg py312=$PY312 \
  --build-arg py313=$PY313 \
  --build-arg py314=$PY314 \
  --build-arg gcc15=$GCC15 \
  -f Dockerfile.agent \
  -t general-purpose-agent:latest .
echo "✅ 'general-purpose-agent' build complete."

echo "🎉 Both Jenkins images are built and ready."
echo "   You can now run '03-deploy-controller.sh'."
```

### Deconstructing the "Build" Script

This script is straightforward but performs one vital task:

1.  **Find Host Docker GID:** The script starts by finding the numerical GID of the `docker` group on the host. This is the solution to our DooD permission challenge.
2.  **Build the Controller Image:** It runs the first `docker build` command, using `-f Dockerfile.controller` to specify our "Foreman" blueprint. Critically, it passes the `--build-arg HOST_DOCKER_GID=$HOST_DOCKER_GID` flag. This injects the host's GID into the build, allowing our `Dockerfile.controller` to "bake in" the correct permissions.
3.  **Build the Agent Image:** It runs the second `docker build` command, using `-f Dockerfile.agent`. This build doesn't need the GID but *does* need the toolchain version arguments (`PY312`, `GCC15`, etc.), which we've hardcoded here to match our `dev-container` environment.

With this script, we now have two custom images, `jenkins-controller:latest` and `general-purpose-agent:latest`, built locally and ready for deployment.

-----

## 6.3. The "Deploy" Script (`03-deploy-controller.sh`)

This is the final assembly. This script takes our newly built `jenkins-controller` image and launches it as a container, connecting all the pieces we've built across this entire series. It connects our network, mounts our configs, passes our secrets, and enables our security.

```bash
#!/usr/bin/env bash

#
# -----------------------------------------------------------
#               03-deploy-controller.sh
#
#  This is the "deploy" script. It runs the 'docker run'
#  command to launch our 'jenkins-controller' container.
#
#  It's responsible for connecting all our "first principles"
#  components together:
#
#  1. Network:    Connects to 'cicd-net' with hostname 'jenkins'.
#  2. Ports:      Publishes the UI (10400) and Agent (10401) ports.
#  3. Secrets:    Passes the *scoped* 'jenkins.env' file.
#  4. Volumes:    Mounts our JCasC config, our .p12 keystore,
#                 the 'jenkins-home' data volume, and the
#                 'docker.sock' for DooD.
#  5. HTTPS:      Passes 'JENKINS_OPTS' to enable SSL using
#                 our .p12 keystore and its password.
# -----------------------------------------------------------

set -e
echo "🚀 Deploying Jenkins Controller..."

# --- 1. Define Paths ---
JENKINS_CONFIG_DIR="$HOME/cicd_stack/jenkins/config"
SCOPED_ENV_FILE="$(pwd)/jenkins.env"

# --- 2. Stop and Remove Old Container (if it exists) ---
# This ensures a clean start
if [ "$(docker ps -q -f name=jenkins-controller)" ]; then
    echo "Stopping existing 'jenkins-controller'..."
    docker stop jenkins-controller
fi
if [ "$(docker ps -aq -f name=jenkins-controller)" ]; then
    echo "Removing existing 'jenkins-controller'..."
    docker rm jenkins-controller
fi

# --- 3. Source Keystore Password from Scoped Env File ---
# We need this *one* variable on the host to build the JENKINS_OPTS string
if [ ! -f "$SCOPED_ENV_FILE" ]; then
    echo "⛔ ERROR: Scoped 'jenkins.env' file not found."
    echo "Please run '01-setup-jenkins.sh' first."
    exit 1
fi
# Source the file to load its variables into our script
source "$SCOPED_ENV_FILE"

if [ -z "$JENKINS_KEYSTORE_PASSWORD" ]; then
    echo "⛔ ERROR: JENKINS_KEYSTORE_PASSWORD not found in 'jenkins.env'."
    exit 1
fi

echo "🔐 Keystore password loaded."

# --- 4. Define Ports (from our 01-setup.sh) ---
JENKINS_HTTPS_PORT="10400"
JENKINS_JNLP_PORT="10401"

# --- 5. Run the Controller Container ---
echo "--- Starting 'jenkins-controller' container ---"

docker run -d \
  --name "jenkins-controller" \
  --restart always \
  --network "cicd-net" \
  --hostname "jenkins.cicd.local" \
  --publish "127.0.0.1:${JENKINS_HTTPS_PORT}:${JENKINS_HTTPS_PORT}" \
  --publish "127.0.0.1:${JENKINS_JNLP_PORT}:${JENKINS_JNLP_PORT}" \
  --env-file "$SCOPED_ENV_FILE" \
  --env "CASC_JENKINS_CONFIG=/var/jenkins_home/casc_configs/" \
  --volume "jenkins-home:/var/jenkins_home" \
  --volume "$JENKINS_CONFIG_DIR:/var/jenkins_home/casc_configs:ro" \
  --volume "/var/run/docker.sock:/var/run/docker.sock" \
  --env JENKINS_OPTS="--httpPort=-1 \
--httpsPort=${JENKINS_HTTPS_PORT} \
--httpsKeyStore=/var/jenkins_home/casc_configs/ssl/jenkins.p12 \
--httpsKeyStorePassword=${JENKINS_KEYSTORE_PASSWORD} \
--webroot=/var/jenkins_home/war \
--sessionTimeout=3600 \
--sessionEviction=3600" \
  jenkins-controller:latest

# We no longer override the entrypoint. The image will
# run its default 'jenkins.sh' command.

echo "✅ Jenkins Controller is starting."
echo "   Monitor logs with: docker logs -f jenkins-controller"
echo ""
echo "   Wait for the 'Jenkins is fully up and running' log message."
echo "   Then, access the UI at: https://jenkins.cicd.local:10400"
echo "   (Remember to add '127.0.0.1 jenkins.cicd.local' to your /etc/hosts file!)"
```

### Deconstructing the "Deploy" Script

This `docker run` command is the final assembly of our entire architecture:

* `--network "cicd-net"` & `--hostname "jenkins.cicd.local"`: Connects our "Foreman" to our "city" network and gives it the FQDN that our CA certificate and GitLab are expecting.
* `--publish "127.0.0.1:..."`: Binds the UI (`10400`) and JNLP (`10401`) ports *only* to the host's `localhost` interface for security.
* `--env-file "$SCOPED_ENV_FILE"`: Passes in our "scoped" `jenkins.env` file, providing all the `${...}` variables that our `jenkins.yaml` needs for secrets.
* `--env "CASC_JENKINS_CONFIG=..."`: This is the magic flag that activates the JCasC plugin and tells it *where* to find our `jenkins.yaml` file.
* `--volume "jenkins-home:..."`: Connects our Docker-managed volume (from Article 1) to store all of Jenkins's data (jobs, build history, etc.).
* `--volume "$JENKINS_CONFIG_DIR:..."`: This is our JCasC mount. We mount our host's `config` directory (which contains our `jenkins.yaml` and the `ssl/jenkins.p12` keystore) into the location specified by `CASC_JENKINS_CONFIG`.
* `--volume "/var/run/docker.sock:..."`: This provides the DooD capability, allowing the controller to spawn agents.
* **The Missing Flag:** Notice there is no `--group-add` flag. Because we "baked" the GID fix into our `Dockerfile.controller`, this runtime flag is no longer necessary.
* `--env JENKINS_OPTS="..."`: This is the final and most critical piece. We use this environment variable to pass start-up commands to the Jenkins Java process. We tell it:
    * `--httpPort=-1`: **Disable HTTP entirely.**
    * `--httpsPort=${JENKINS_HTTPS_PORT}`: Enable HTTPS on our specified port.
    * `--httpsKeyStore=...`: Point to the `.p12` keystore file we just mounted.
    * `--httpsKeyStorePassword=...`: Provide the password (which we sourced from `jenkins.env`) to unlock the keystore.

This command launches our controller, which will now boot up, read our `jenkins.yaml`, configure itself, and be fully secured with our custom SSL certificate.

# Chapter 7: Verification & First Login

With our `03-deploy-controller.sh` script running, the Jenkins controller will take a few minutes to boot, load all the plugins, and process our `jenkins.yaml` file. You can monitor this process with `docker logs -f jenkins-controller`. Once you see the "Jenkins is fully up and running" log message, our "Foreman" is ready for inspection.

-----

## 7.1. Verification (UI): First Login & The JCasC Payoff

First, we'll verify the User Interface. Open your browser and navigate to the controller's FQDN:

**`https://jenkins.cicd.local:10400`**

(Remember, this only works because you've edited your `/etc/hosts` file, as we did in the GitLab article).

You should immediately see three signs of success:

1.  **A Secure Lock Icon:** Your browser trusts the Jenkins UI. This proves our entire SSL chain is working: your host's OS trusts our Local CA (from Article 2), and the controller is correctly serving its `jenkins.p12` keystore (from our `JENKINS_OPTS` flag).
2.  **No "Unlock Jenkins" Screen:** The JCasC plugin has worked. We are not asked to find a secret password in a log file.
3.  **A Login Page:** We are taken directly to the login page.

Now, log in using the credentials we defined in our `jenkins.yaml` file (via the `jenkins.env`):

* **Username:** `admin`
* **Password:** (The `JENKINS_ADMIN_PASSWORD` you set)

Once logged in, let's confirm JCasC did its job. Navigate to **Manage Jenkins** in the left sidebar:

* **Check Credentials:** Go to **Credentials**. You should see our two JCasC-defined credentials: **`gitlab-api-token`** and **`gitlab-checkout-credentials`**. This proves the `credentials:` block worked.
* **Check Cloud Config:** Go to **Clouds**. You will see our **`docker-local`** cloud. Click **Configure**. You'll see it's correctly set up to use our `general-purpose-agent` and `cicd-net`. This proves the `clouds:` block worked.

-----

## 7.2. Verification (API): The `403 Forbidden` Debugging Journey

The UI is working, but the most critical verification is to test the API. We will use our `04-verify-jenkins.py` script to do this.

This verification was one of our most complex debugging challenges. Our first attempts to connect—even with a valid user and password—failed with an `HTTP Error 403: Forbidden`. This wasn't an *authentication* failure (the server knew who we were); it was an *authorization* failure (it was blocking our request).

Our investigation revealed two key facts about the Jenkins API:

1.  **API Tokens are Required:** Jenkins blocks password-based authentication for most of its API, especially high-security endpoints like `/scriptText`. The correct way to authenticate is with an API Token.
2.  **`urllib` Auth is Complex:** Our attempts to use `urllib`'s "smart" handlers (like `HTTPBasicAuthHandler` and `HTTPCookieProcessor`) created a state-management conflict. The handlers would send a session cookie *and* a token, or a token *and* a crumb, confusing the server and resulting in a 403.

The solution was to stop being "smart" and to be explicit. We must **manually build the `Authorization: Basic` header** ourselves and send *only* that. This is the most direct and reliable way to authenticate.

### Action 1: Manually Generate an API Token

First, we must generate the API token for our `admin` user. JCasC cannot do this for us.

1.  In the Jenkins UI, click your `admin` username (top right).
2.  In the left-hand sidebar, click **Security**.
3.  Find the **"API Token"** section.
4.  Click **"Add new Token"**, give it a name (like `admin-api-token`), and click **"Generate"**.
5.  **Copy the generated token immediately.** You will not see it again.
6.  Open your `jenkins.env` file (in your `0008_...` article directory) and add this token as `JENKINS_API_TOKEN`. (Our `01-setup-jenkins.sh` already added `GITLAB_CHECKOUT_TOKEN`, but we must add this one manually).

### Action 2: Run the Verification Script

The following script, `04-verify-jenkins.py`, is our final, working solution. It reads the `JENKINS_API_TOKEN` from our `jenkins.env` file, manually base64-encodes it into a Basic Auth header, and sends it with a simple Groovy script to test our access.

```python
#!/usr/bin/env python3

import os
import ssl
import json
import urllib.request
import urllib.parse
import base64
from pathlib import Path

# --- Configuration ---
ENV_FILE_PATH = Path.cwd() / "jenkins.env"
JENKINS_URL = "https://jenkins.cicd.local:10400"
JENKINS_USER = "admin"

# --- 1. Standard Library .env parser ---
def load_env(env_path):
    """
    Reads a .env file and loads its variables into os.environ.
    """
    print(f"Loading environment from: {env_path}")
    if not env_path.exists():
        print(f"⛔ ERROR: Environment file not found at {env_path}")
        print("Please run '01-setup-jenkins.sh' first.")
        return False

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                os.environ[key] = value
    return True

# --- 2. Main Verification ---
def verify_jenkins_api(base_url, username, api_token):
    """
    Connects to Jenkins using a manually-crafted Basic Auth
    header (token) and attempts an authenticated API call.
    This method does not use or need a CSRF crumb.
    """

    print("Creating default SSL context...")
    # This proves our host's CA trust (from Article 2) is working
    context = ssl.create_default_context()

    print("Attempting authenticated API call (Groovy script)...")
    script_url = f"{base_url}/scriptText"

    # This simple script just tests the connection.
    groovy_script = "return jenkins.model.Jenkins.get().getSystemMessage()"
    data = urllib.parse.urlencode({'script': groovy_script}).encode('utf-8')

    # --- Manually build the Authorization Header ---
    # This was the solution to our 403 Forbidden errors.
    auth_string = f"{username}:{api_token}"
    auth_bytes = auth_string.encode('utf-8')
    auth_base64 = base64.b64encode(auth_bytes).decode('ascii')

    headers = {
        'Authorization': f"Basic {auth_base64}",
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    # We do NOT send a Jenkins-Crumb header.

    req = urllib.request.Request(script_url, data=data, headers=headers, method='POST')

    try:
        # We use the default urlopen, passing our context.
        with urllib.request.urlopen(req, context=context) as response:
            if response.status == 200:
                result = response.read().decode()
                print(f"✅✅✅ Jenkins Verification SUCCESS! ✅✅✅")
                print(f"Authenticated API call returned: {result}")
            else:
                print(f"⛔ ERROR: API call failed. Status: {response.status}")
                print(f"   Response: {response.read().decode()}")

    except urllib.error.URLError as e:
        print(f"⛔ ERROR: Connection failed. Did you add '127.0.0.1 jenkins.cicd.local' to /etc/hosts?")
        print(f"   Details: {e}")
        if hasattr(e, 'read'):
            print(f"  Response: {e.read().decode()}")
    except Exception as e:
        print(f"⛔ ERROR: API call failed.")
        print(f"   Details: {e}")
        if hasattr(e, 'read'):
            print(f"  Response: {e.read().decode()}")

# --- 6. Main execution ---
if __name__ == "__main__":
    if not load_env(ENV_FILE_PATH):
        exit(1)

    JENKINS_TOKEN = os.getenv('JENKINS_API_TOKEN')

    if not JENKINS_TOKEN:
        print("⛔ ERROR: JENKINS_API_TOKEN not found in 'jenkins.env'")
        print("Please generate one in the UI and add it to the file.")
        exit(1)

    verify_jenkins_api(JENKINS_URL, JENKINS_USER, JENKINS_TOKEN)
```

### The Payoff

When you run this script (`python3 04-verify-jenkins.py`), you will see the successful output. This proves our API is accessible, our token is valid, and our JCasC-defined `admin` user has the correct `Overall/Administer` permissions to access the script console. Our "Foreman" is fully operational and ready to work.


# Chapter 8: Practical Application - The "Hero Project" Pipeline (V1)

Our "Factory Foreman" (Jenkins) is fully operational. We've verified its UI is secure, its API is accessible, and its "hiring department" (the Docker Cloud) is correctly configured. The infrastructure is complete.

Now it's time to put it to work.

The goal of this chapter is to connect our "Factory" to our "Central Library" (GitLab) and run our first *real* build. We will connect Jenkins to our `0004_std_lib_http_client` "hero project" and use its "polyglot" build agent to compile, test, and run our C++, Rust, and Python code.

-----

## 8.1. Action 1: The `Jenkinsfile` (V1)

Our first step is to create the "assembly line" instructions. As we discussed in Chapter 2, these instructions live *with the code*. We will create a new file named `Jenkinsfile` (with no extension) in the root of our `0004_std_lib_http_client` repository.

This file is a "declarative pipeline" script. It tells the Jenkins agent *what* to do and in *what order*. Here is the complete V1 `Jenkinsfile` for our project.

```groovy
// Jenkinsfile

pipeline {
    // 1. Define our "Worker"
    // This tells Jenkins to spin up our custom-built agent
    // which already has all system dependencies (cmake, rust, python).
    agent {
        label 'general-purpose-agent'
    }

    stages {
        // 2. Setup & Build Stage
        // This runs the project's own setup.sh.
        // It will create the Python venv, install pip requirements,
        // and compile both the Debug and Release builds.
        stage('Setup & Build') {
            steps {
                echo '--- Running project setup.sh ---'
                sh 'chmod +x ./setup.sh'
                sh './setup.sh'
            }
        }

        // 3. Test & Coverage Stage
        // This runs the project's coverage script, which
        // depends on the 'build_debug' created in the prior stage.
        stage('Test & Coverage') {
            steps {
                echo '--- Running CTest, Cargo-Cov, and Pytest ---'
                sh 'chmod +x ./run-coverage.sh'
                sh './run-coverage.sh'
            }
        }
    }
}
```

### Deconstructing the `Jenkinsfile`

This simple file is incredibly powerful because it leans on the work we've already done.

* **`agent { label 'general-purpose-agent' }`**
  This is the "hiring" instruction. It tells the Jenkins controller to request a new "worker" from the cloud named `docker-local` that has the label `general-purpose-agent`. This label matches *exactly* what we defined in our `jenkins.yaml` file, which in turn points to our `general-purpose-agent:latest` Docker image.

* **`stage('Setup & Build')`**
  This is our first assembly line station. Instead of cluttering our pipeline with `cmake` and `python` commands, we simply make our scripts executable (`chmod +x`) and run the project's own `setup.sh`. This is a clean separation of concerns: the `Jenkinsfile` orchestrates *what* to do, and the `setup.sh` script knows *how* to do it. This stage will create the Python venv and build both the Debug and Release versions of our libraries.

* **`stage('Test & Coverage')`**
  This is our "quality assurance" station. Once the build is complete, it runs the `run-coverage.sh` script. This script executes all three test suites (C/C++ `ctest`, Rust `cargo llvm-cov`, and Python `pytest`) against the `build_debug` directory created in the previous stage.

Now, **add this `Jenkinsfile` to the root of your `0004_std_lib_http_client` project, commit it, and push it to your GitLab server.**

Our "blueprint" is now in the "Library," waiting for the "Foreman" to find it.

### A Note on Credentials: Creating Your Project Access Token

Before our `Jenkinsfile` can work, it needs permission to clone our private `0004_std_lib_http_client` repository. We will give it this permission by creating a new, limited-scope **Project Access Token** in GitLab.

This token is the value we will store as `GITLAB_CHECKOUT_TOKEN` in our `cicd.env` file. It's crucial to do this *before* you deploy Jenkins, so that when the controller starts, our JCasC file can read this token and create the permanent `gitlab-checkout-credentials` credential.

If you haven't created this token yet, follow these steps:

1.  **Navigate to Your Project:** Open your GitLab instance and go to the `0004_std_lib_http_client` project.
2.  **Go to Access Tokens:** In the project's left-hand sidebar, navigate to **Settings \> Access Tokens**.
3.  **Add New Token:** Click the **"Add new token"** button.
4.  **Fill out the form:**
    * **Name:** `jenkins-checkout-token`
    * **Role:** Select `Developer`. This provides just enough permission to clone the repository.
    * **Scopes:** Check the box for **`read_repository`**. This is the *only* scope this token needs, following the Principle of Least Privilege.
5.  **Create and Copy:** Click the **"Create project access token"** button. GitLab will display the token one time. Copy this token.
6.  **Update Your `cicd.env`:** Open your master `cicd.env` file (in `~/cicd_stack/`) and add this token:
    ```
    GITLAB_CHECKOUT_TOKEN="glpat-..."
    ```
7.  **Update `jenkins.env`:** Open your `jenkins.env` file (in the Jenkins article directory) and add the same line:
    ```
    GITLAB_CHECKOUT_TOKEN="glpat-..."
    ```

Now, when you run your `01-setup-jenkins.sh` and `03-deploy-controller.sh` scripts, our JCasC file will automatically read this token and create the permanent `gitlab-checkout-credentials` in Jenkins. If you add this credential manually in the UI, **it will be deleted the next time your controller restarts.**

## 8.2. Action 2: Jenkins UI (Create the Job)

With our `Jenkinsfile` pushed to the repository, our "Foreman" (Jenkins) is ready to be given its assignment. We need to create a job that tells Jenkins to "watch" this specific GitLab project.

We will use the **"Multibranch Pipeline"** job type. This is a powerful feature provided by our `gitlab-branch-source` plugin. Instead of creating a separate, static job for our `main` branch, we will create one "project" job that *automatically* discovers all branches, merge requests, and tags that contain a `Jenkinsfile` and creates jobs for them.

Here are the steps to set this up:

1.  **Log in to Jenkins** at `https://jenkins.cicd.local:10400` as your `admin` user.
2.  From the dashboard, you can create a folder for organization (e.g., "Articles") or create the job directly. Click **"New Item"** in the left sidebar.
3.  **Enter an item name:** `0004_std_lib_http_client`
4.  Select **"Multibranch Pipeline"** from the list of job types and click **"OK"**.
5.  You'll be taken to the configuration page. Scroll down to the **"Branch Sources"** section.
6.  Click **"Add source"** and select **"GitLab project"**. This option is only here because we installed the `gitlab-branch-source` plugin.
7.  Fill out the source configuration:
    * **Server:** Select **"Local GitLab"**. This is the server connection we defined in our `jenkins.yaml` file.
    * **Owner:** Select your GitLab group, **"Articles"**. Jenkins will use the `gitlab-api-token` (defined in JCasC) to scan this group for projects.
    * **Project:** A dropdown will appear. Select **`0004_std_lib_http_client`**.
    * **Checkout Credentials:** This is the solution to our "authentication failed" problem. In the dropdown, select our JCasC-defined credential: **`gitlab-checkout-bot / ******`**. This tells Jenkins to use our limited-scope Project Access Token for all `git clone` operations.

8.  Click **"Save"**.

As soon as you save, Jenkins will automatically perform an initial "Branch Indexing" scan. You can watch the log for this scan in the "Scan Multibranch Pipeline Log" in the sidebar. It will connect to GitLab (proving our controller's JVM trust), find your `main` branch, see the `Jenkinsfile`, and create a new job for it.

---
## 8.3. Action 3: GitLab UI (Set the Webhook)

At this point, our job exists, but it doesn't know *when* we push new code. We could tell Jenkins to "Periodically scan," but this is inefficient. We want an instant, event-driven trigger.

The solution is a **webhook**. We need to tell GitLab to send a "ping" to Jenkins every time we create a Merge Request.

Normally, this is a manual step, but our plugin stack has a final surprise for us:

1.  In your browser, go to your GitLab project: `https://gitlab.cicd.local:10300/Articles/0004_std_lib_http_client`.
2.  In the left sidebar, go to **Settings > Webhooks**.

You will see that a webhook pointing to our Jenkins instance **already exists**.

This is the final payoff of our JCasC setup. When we configured the "Local GitLab" server in our `jenkins.yaml` and set `manageWebHooks: true`, we gave Jenkins (using its `gitlab-api-token`) permission to *automatically* create this webhook for us when we created the Multibranch job.

**All we have to do is test it and tweak it:**

1.  Click the **"Edit"** button for the auto-generated webhook.
2.  **Tweak Triggers:** By default, it's likely set for "Push events." We want to follow our professional workflow. **Uncheck "Push events"** and ensure **"Merge request events"** is **checked**.
3.  **Test the Connection:** Scroll down and click the **"Test"** button. Select **"Merge request events"** from the dropdown and click **"Test webhook"**.

At the top of the page, you will see a green **`Hook executed successfully: HTTP 200`** message.

This single message proves our entire security architecture is working end-to-end. It confirms that GitLab (whose JVM trusts our CA) successfully sent a secure HTTPS request to our Jenkins controller (which is serving traffic using its `.p12` keystore). The "Factory" and the "Library" are now fully and securely connected.

### A Note on Advanced Triggers: The V2 Pipeline

For our V1 pipeline, we've configured the webhook to trigger *only* on "Merge request events." This is a robust and common workflow that ensures we only run our full, expensive build and test suite when we're preparing to merge code.

However, this is just the beginning. A more sophisticated, real-world pipeline would use **conditional logic** to run *different* sets of tasks based on the *type* of trigger.

It is entirely possible (and standard practice) to enable both **"Push events"** and **"Merge request events."** We would then make our `Jenkinsfile` "smarter" by using its `when` directive to inspect the build's context.

For example, in a V2 pipeline, we could configure:
1.  **On a simple `git push` to a feature branch:** The `Jenkinsfile` would detect `env.BRANCH_NAME != 'main'` and `when { NOT { changeRequest() } }`. It would then *only* run fast jobs like linting and unit tests, giving the developer feedback in seconds.
2.  **On a `push` to a Merge Request:** The `Jenkinsfile` would detect `when { changeRequest() }`. This would trigger our *full* validation pipeline: build, all tests (C++, Rust, Python), and coverage. This is our "quality gate."
3.  **On a merge to the `main` branch (or a Git tag):** The `Jenkinsfile` would detect `env.BRANCH_NAME == 'main'`. This would run the full pipeline *plus* our new "Publish" stage (which we'll build in the next article) to save the compiled artifacts to Artifactory.

We have started with a simple, effective "build everything on MR" strategy. We will build on this foundation later to create these more complex, conditional workflows.

# Chapter 9: The Payoff - The First Automated Build

Our infrastructure is 100% complete. Our `Jenkinsfile` is in the repository, our Jenkins job is configured to use our JCasC-defined credentials, and the GitLab webhook is automatically set up and tested.

All that's left is to see it in action.

---
## 9.1. The "Scan"

When you first created the "Multibranch Pipeline" job in the last chapter, Jenkins automatically performed an initial "Branch Indexing" scan. In the "Scan Multibranch Pipeline Log" (or by clicking "Scan Repository Now"), you would have seen Jenkins:

1.  Connect to `https://gitlab.cicd.local` (proving the controller's JVM trust).
2.  Use the `gitlab-api-token` to scan the `Articles/0004_std_lib_http_client` project.
3.  Discover the `main` branch.
4.  Find the `Jenkinsfile` in that branch.
5.  Automatically create a new pipeline job named "main" and queue it for a build.

This first build is the complete validation of our setup.

---
## 9.2. The "Build": Deconstructing the Success Log

When you open the log for that first successful build, you are seeing the payoff for every single piece of our architecture. Let's narrate the log:

1.  **`Provisioning 'general-purpose-agent...'`**
    This first line is a triumph. It proves our "Foreman" (Controller) has successfully used the **Docker Plugin** (configured by JCasC) to begin "hiring" our worker.

2.  **No "Pulling image..." Step**
    You'll notice the log does *not* show a "Pulling image..." step. It immediately moves to creating the container. This proves our **`pullStrategy: 'PULL_NEVER'`** setting in `jenkins.yaml` is working, forcing the controller to use our local image.

3.  **`Started container ID ...` & `Accepted JNLP4-connect connection...`**
    This is the proof that our agent is working. The container started *without* the `exec: "-url": executable file not found` error. This confirms our **`ENTRYPOINT ["java", "-jar", ...]`** instruction in `Dockerfile.agent` is correct. The agent is up and connected.

4.  **`using credential std-lib-http-client` & `git clone ...`**
    The `git clone` succeeds. This proves two things:
    * Our JCasC-defined **`gitlab-checkout-credentials`** are working.
    * Our agent's **OS-level trust** (`update-ca-certificates`) is working, allowing `git` to trust `https://gitlab.cicd.local`.

5.  **`Found Rust: /home/jenkins/.rustup/toolchains...`**
    This confirms our `Dockerfile.agent` build process was correct. `cmake` is running as the `jenkins` user and is finding the Rust toolchain in `/home/jenkins/.cargo/bin` because we installed it under the correct user and added it to the `PATH`.

6.  **`[100%] Built target...` & `100% tests passed...`**
    The `setup.sh` and `run-coverage.sh` scripts complete. Our polyglot build—C++, Rust, and Python—has been successfully built and tested by our custom, ephemeral agent.

7.  **`Finished: SUCCESS`**
    The pipeline is complete. The agent container is automatically destroyed, along with all its build files.

---
## 9.3. The "Trigger": The Final Verification

The manual scan proves the build works. This final test proves the *automation* works. We will now simulate a developer's workflow and watch the entire loop trigger automatically.

1.  First, we'll go to the GitLab Webhooks page and show that the `gitlab-branch-source` plugin **automatically created the webhook for us**. We'll use the "Test" button to prove the `HTTP 200` connection.

2.  Then, we'll guide the user to make a *real* change: `git checkout -b feature/test-trigger`, add a comment, `git push`, and **open a new Merge Request in GitLab**.

3.  We'll watch the Jenkins UI as the `MR-1` build appears *instantly*, proving the webhook is functioning perfectly.

This confirms our "Factory" and "Library" are perfectly connected.

# Chapter 10: Conclusion

## 10.1. What We've Built

We have successfully built a complete, automated, and scalable CI (Continuous Integration) system. Our "Factory Foreman" (Jenkins) is fully operational and perfectly integrated with our "Central Library" (GitLab).

Let's summarize what our new system accomplishes:
* **Fully Automated Builds:** When a developer opens a Merge Request, a build is triggered *instantly* and automatically, with no human intervention.
* **Secure & Trusted:** The entire connection is secured with our internal CA. GitLab sends a secure webhook to Jenkins, and Jenkins clones from GitLab over a trusted HTTPS connection.
* **Scalable & Isolated Compute:** We are using a modern "Controller/Agent" architecture. The controller only orchestrates, and the *real* work is done by our `general-purpose-agent` containers. This means we can run multiple builds in parallel, each in its own clean, isolated environment.
* **Consistent, Polyglot Environment:** Our custom agent image, built with our "dual-trust" fix and the correct user-context, is proven to work. It can build and test our complex C++, Rust, and Python project in a single, unified pipeline.

---
## 10.2. The New Problem: The "Ephemeral Artifact"

Our pipeline log `Finished: SUCCESS` is a huge victory, but it also highlights our next major challenge. Our `setup.sh` script successfully compiled our C++ library (`libhttpc.so`), our Rust binaries, and our Python wheel (`.whl`), and `run-coverage.sh` proved they work.

But what happened to them?

They were created inside the `general-purpose-agent` container. The moment the build finished, that container was **immediately and permanently destroyed**, taking all those valuable, compiled "finished goods" with it.

Our factory is running at 100% capacity, but we're just throwing every finished product into the incinerator. We have a "build," but we have no *artifacts*.

---
## 10.3. Next Steps: Building the "Secure Warehouse"

Our "factory" is missing its "loading dock" and "warehouse."

We need a central, persistent, and secure location to *store* our finished products. We need a system that can:
1.  Receive the compiled `libhttpc.so`, the `httprust_client` binary, and the `httppy-0.1.0-py3-none-any.whl` file from our build agent.
2.  Store them permanently and give them a version number.
3.  Allow other developers or servers to download and use these "blessed" artifacts without having to rebuild the entire project themselves.

This is the exact role of an **Artifact Repository Manager**. In the next article, we will build our "Secure Warehouse": **JFrog Artifactory**. We will then add a final "Publish" stage to our `Jenkinsfile` to solve this "ephemeral artifact" challenge once and for all.
