//! Which builder plain `docker build` uses: Docker's own, or ctrs's.
//!
//! On a machine with no other engine, ctrs's, without asking. On one with
//! OrbStack, Docker Desktop or another engine, the window asks once
//! ("Keep building with Docker" is the default), and Settings → Builds
//! switches it any time, at once, in terminals already open too.
//!
//! How the docker CLI picks a builder: `docker build` (and `docker
//! builder`) is handed to buildx with `BUILDX_BUILDER=<current context>`,
//! unless the config's `builder` alias is set (`docker buildx install`),
//! in which case buildx takes its current builder (`~/.docker/buildx/current`).
//! Compose and `docker buildx build` take buildx's current builder.
//!
//! - Always: a buildx builder named `ctrs`, a copy of ctrs's builder
//!   (`ctrs-build`: the same BuildKit and cache), so a user's own context
//!   named `ctrs` builds on ctrs and loads into ctrs, where buildx would
//!   otherwise ask the engine for a BuildKit of its own, which ctrs doesn't
//!   have. ctrs never creates that context; the user may.
//! - Build with Docker: nothing more. Builds follow docker's context, as
//!   they did before ctrs: OrbStack's builds stay OrbStack's, and once
//!   docker uses ctrs, builds run on ctrs.
//! - Build with ctrs: the `builder` alias, and ctrs's builder as buildx's
//!   current builder for every context (what `docker buildx use --global`
//!   writes). `docker build`, `docker compose build` and `docker buildx
//!   build` run on ctrs and load into ctrs whatever context docker uses.
//!   Everything else (`docker run`, `ps`, `compose up`…) still follows the
//!   context, so an image built this way is in ctrs, not in Docker
//!   Desktop's store.
//!
//! What ctrs changes for "Build with ctrs" (the alias and buildx's current
//! builder) is kept as it was in `build.json` first, and choosing Docker
//! puts it back exactly, unless something else has changed it since.
//! `ctrs build` always builds on ctrs, whichever is chosen.
//!
//! The same file serves the Mac and Linux (`ctrs build-with`, the window)

use std::io;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};

/// Docker's builder, or ctrs's.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum With {
    Docker,
    Ctrs,
}

impl With {
    pub fn parse(s: &str) -> Option<With> {
        match s {
            "docker" => Some(With::Docker),
            "ctrs" => Some(With::Ctrs),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            With::Docker => "docker",
            With::Ctrs => "ctrs",
        }
    }
}

/// Where everything is: docker's config directory, buildx's, ctrs's
/// `build.json`, and ctrs's builder and context names.
#[derive(Debug, Clone)]
pub struct Places {
    pub docker: PathBuf,
    pub buildx: PathBuf,
    pub state: PathBuf,
    pub builder: String,
    pub context: String,
}

fn read_json(path: &Path) -> io::Result<Value> {
    match std::fs::read(path) {
        // A BOM, as some editors prepend: docker tolerates none, but reading
        // through one costs nothing.
        Ok(b) => serde_json::from_slice(b.strip_prefix(b"\xEF\xBB\xBF").unwrap_or(&b)).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{}: {e}", path.display()))),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(json!({})),
        Err(e) => Err(e),
    }
}

/// Through a temporary file, so a crash never leaves half a file.
fn write_bytes(path: &Path, bytes: &[u8]) -> io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let tmp = path.with_extension("ctrs-tmp");
    std::fs::write(&tmp, bytes)?;
    std::fs::rename(tmp, path)
}

fn write_json(path: &Path, v: &Value) -> io::Result<()> {
    write_bytes(path, &serde_json::to_vec_pretty(v).map_err(io::Error::other)?)
}

impl Places {
    fn config(&self) -> PathBuf {
        self.docker.join("config.json")
    }

    fn current(&self) -> PathBuf {
        self.buildx.join("current")
    }

    fn instance(&self, name: &str) -> PathBuf {
        self.buildx.join("instances").join(name)
    }

    fn state(&self) -> Value {
        read_json(&self.state).unwrap_or_else(|_| json!({}))
    }

    /// What was chosen (or set for a machine with no other engine).
    pub fn saved(&self) -> Option<With> {
        self.state()["with"].as_str().and_then(With::parse)
    }

    /// Whether to ask: another engine is here, and nobody has chosen. A
    /// choice ctrs made by itself on a machine that had none at the time is
    /// asked about once another engine appears.
    pub fn ask(&self, other: Option<&str>) -> bool {
        let s = self.state();
        other.is_some() && (s["with"].is_null() || s["auto"] == true)
    }

    /// Whether ctrs's builder is in buildx's store yet.
    pub fn ready(&self) -> bool {
        self.instance(&self.builder).is_file()
    }

    /// Whether `docker build` goes to ctrs's builder in every context now.
    pub fn taken(&self) -> bool {
        let cfg = read_json(&self.config()).unwrap_or_default();
        let cur = read_json(&self.current()).unwrap_or_default();
        cfg["aliases"]["builder"] == "buildx" && cur["Name"] == self.builder.as_str() && cur["Global"] == true
    }

    /// The builder named after ctrs's context: ctrs's builder under that
    /// name. Left alone if one of that name is there that isn't a copy of
    /// ctrs's.
    fn shadow(&self) -> io::Result<()> {
        let ours = read_json(&self.instance(&self.builder))?;
        if ours.get("Name").is_none() {
            return Ok(()); // Not made yet.
        }
        let path = self.instance(&self.context);
        let theirs = read_json(&path)?;
        if theirs.get("Name").is_some() && !self.copied(&theirs) {
            return Ok(());
        }
        let mut copy = ours;
        copy["Name"] = self.context.as_str().into();
        if theirs != copy {
            write_bytes(&path, &serde_json::to_vec(&copy).map_err(io::Error::other)?)?;
        }
        Ok(())
    }

    /// Whether a builder is ctrs's copy: its nodes are ctrs's builder's.
    fn copied(&self, instance: &Value) -> bool {
        let nodes = instance["Nodes"].as_array().map(Vec::as_slice).unwrap_or_default();
        !nodes.is_empty() && nodes.iter().all(|n| n["Name"].as_str().is_some_and(|name| name.starts_with(&self.builder)))
    }

    fn save(&self, with: With, auto: bool) -> io::Result<()> {
        let mut s = self.state();
        s["with"] = with.name().into();
        s["auto"] = auto.into();
        write_json(&self.state, &s)
    }

    /// Build with ctrs: the alias and the global current builder, after
    /// keeping what was there. False if ctrs's builder isn't made yet (it
    /// is taken once it is: `apply`).
    fn take(&self) -> io::Result<bool> {
        if !self.ready() {
            return Ok(false);
        }
        let mut s = self.state();
        if s["before"].is_null() {
            let cfg = read_json(&self.config())?;
            let current = match std::fs::read_to_string(self.current()) {
                Ok(t) => Value::String(t),
                Err(e) if e.kind() == io::ErrorKind::NotFound => Value::Null,
                Err(e) => return Err(e),
            };
            s["before"] = json!({"alias": cfg["aliases"]["builder"], "aliases": cfg.get("aliases").is_some(), "current": current});
            write_json(&self.state, &s)?;
        }
        let mut cfg = read_json(&self.config())?;
        if !cfg["aliases"].is_object() {
            cfg["aliases"] = json!({});
        }
        if cfg["aliases"]["builder"] != "buildx" {
            cfg["aliases"]["builder"] = "buildx".into();
            write_json(&self.config(), &cfg)?;
        }
        // buildx's own format, as `docker buildx use --global` writes it.
        let current = json!({"Key": self.context, "Name": self.builder, "Global": true});
        write_bytes(&self.current(), current.to_string().as_bytes())?;
        Ok(true)
    }

    /// Build with Docker: puts back what `take` kept, where it is still
    /// as ctrs left it. Also when ctrs's program is gone (appwatch.rs):
    /// the choice itself is kept, so `apply` takes it again later.
    pub fn give_back(&self) -> io::Result<()> {
        let mut s = self.state();
        let before = s["before"].take();
        if before.is_null() {
            return Ok(());
        }
        let mut cfg = read_json(&self.config())?;
        if cfg["aliases"]["builder"] == "buildx" {
            match &before["alias"] {
                Value::Null => {
                    if let Some(a) = cfg["aliases"].as_object_mut() {
                        a.remove("builder");
                    }
                    if before["aliases"] != true
                        && cfg["aliases"].as_object().is_some_and(serde_json::Map::is_empty)
                        && let Some(o) = cfg.as_object_mut()
                    {
                        o.remove("aliases");
                    }
                }
                was => cfg["aliases"]["builder"] = was.clone(),
            }
            write_json(&self.config(), &cfg)?;
        }
        let cur = read_json(&self.current()).unwrap_or_default();
        if cur["Name"] == self.builder.as_str() && cur["Global"] == true {
            match before["current"].as_str() {
                Some(t) => write_bytes(&self.current(), t.as_bytes())?,
                None => match std::fs::remove_file(self.current()) {
                    Err(e) if e.kind() != io::ErrorKind::NotFound => return Err(e),
                    _ => {}
                },
            }
        }
        if let Some(o) = s.as_object_mut() {
            o.remove("before");
        }
        write_json(&self.state, &s)
    }

    /// What was chosen, made so: called whenever ctrs's builder has been
    /// (re)made. Never fights a change made since, such as a `docker buildx
    /// use` of the user's own: only choosing again does that.
    pub fn apply(&self, other: Option<&str>) -> io::Result<()> {
        self.shadow()?;
        let s = self.state();
        match self.saved() {
            Some(With::Ctrs) if s["before"].is_null() => self.take().map(drop),
            Some(With::Docker) => self.give_back(),
            None if other.is_none() => {
                self.save(With::Ctrs, true)?;
                self.take().map(drop)
            }
            _ => Ok(()),
        }
    }

    /// The user's choice, kept and made so now.
    pub fn choose(&self, with: With) -> io::Result<()> {
        self.save(with, false)?;
        self.shadow()?;
        match with {
            With::Ctrs => self.take().map(drop),
            With::Docker => self.give_back(),
        }
    }

    /// For the window: {with, ask, engine, taken, ready, builder, context}.
    pub fn status(&self, other: Option<&str>) -> Value {
        // Not chosen yet: Docker's, which is what happens until someone does.
        let with = self.saved().unwrap_or(if other.is_some() { With::Docker } else { With::Ctrs });
        json!({"type": "buildwith", "with": with.name(), "ask": self.ask(other), "engine": other, "taken": self.taken(), "ready": self.ready(), "builder": self.builder, "context": self.context})
    }
}

fn docker_dir(home: &Path) -> PathBuf {
    std::env::var_os("DOCKER_CONFIG").filter(|d| !d.is_empty()).map_or_else(|| home.join(".docker"), PathBuf::from)
}

fn buildx_dir(docker: &Path) -> PathBuf {
    std::env::var_os("BUILDX_CONFIG").filter(|d| !d.is_empty()).map_or_else(|| docker.join("buildx"), PathBuf::from)
}

#[cfg(unix)]
pub fn places() -> io::Result<Places> {
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| io::Error::other("HOME is not set"))?;
    let docker = docker_dir(&home);
    Ok(Places {
        buildx: buildx_dir(&docker),
        docker,
        state: home.join(".local/share/ctrs").join("build.json"),
        builder: crate::builds::BUILDER.to_owned(),
        context: "ctrs".to_owned(),
    })
}

/// The engine besides ctrs on this machine, by name, if there is one.
#[cfg(unix)]
pub fn other_engine() -> Option<&'static str> {
    let home = PathBuf::from(std::env::var_os("HOME")?);
    let ours = crate::client::socket().ok().and_then(|s| s.canonicalize().ok());
    // A socket that is ctrs's own (a /var/run/docker.sock pointing at ctrs) isn't another engine.
    let live = |p: &Path| p.exists() && p.canonicalize().ok() != ours;
    let name = |p: &Path| {
        let t = p.canonicalize().unwrap_or_else(|_| p.to_path_buf()).to_string_lossy().into_owned();
        if t.contains(".orbstack") {
            "OrbStack"
        } else if t.contains("/.docker/") {
            "Docker Desktop"
        } else if t.contains("/.rd/") {
            "Rancher Desktop"
        } else if t.contains("/.colima/") {
            "Colima"
        } else if t.contains("podman") {
            "Podman"
        } else {
            "Docker"
        }
    };
    let xdg = std::env::var_os("XDG_RUNTIME_DIR").map(PathBuf::from);
    let sockets = [
        home.join(".orbstack/run/docker.sock"),
        home.join(".docker/run/docker.sock"),
        home.join(".docker/desktop/docker.sock"),
        home.join(".rd/docker.sock"),
        home.join(".colima/default/docker.sock"),
        PathBuf::from("/var/run/docker.sock"),
        PathBuf::from("/run/docker.sock"),
        PathBuf::from("/run/podman/podman.sock"),
    ];
    if let Some(s) = sockets.iter().chain(xdg.map(|x| x.join("podman/podman.sock")).as_ref()).find(|s| live(s)) {
        return Some(name(s));
    }
    // Installed, though not running now.
    let apps: &[(&str, &str)] = if cfg!(target_os = "macos") {
        &[("/Applications/OrbStack.app", "OrbStack"), ("/Applications/Docker.app", "Docker Desktop"), ("/Applications/Rancher Desktop.app", "Rancher Desktop")]
    } else {
        &[("/usr/bin/dockerd", "Docker"), ("/opt/docker-desktop", "Docker Desktop"), ("/opt/rancher-desktop", "Rancher Desktop")]
    };
    apps.iter().find(|(p, _)| Path::new(p).exists()).map(|(_, n)| *n)
}

/// After ctrs's builder is (re)made: what was chosen, made so.
pub fn apply() -> io::Result<()> {
    places()?.apply(other_engine())
}

/// `ctrs build-with [docker|ctrs]`: says which, or switches.
#[cfg(unix)]
pub fn cli(args: &[String]) -> io::Result<()> {
    let p = places()?;
    let other = other_engine();
    if let Some(a) = args.first() {
        let with = With::parse(a).ok_or_else(|| io::Error::other("usage: ctrs build-with [docker|ctrs]"))?;
        p.choose(with)?;
        if with == With::Ctrs && !p.ready() {
            crate::builds::ensure_builder();
        }
    }
    let s = p.status(other);
    let builder = &p.builder;
    match (s["with"].as_str(), other) {
        (Some("ctrs"), _) if !p.ready() => println!("docker build builds on ctrs once its builder `{builder}` is made (`ctrs build-with ctrs` makes it)"),
        (Some("ctrs"), Some(o)) => println!("docker build and docker compose build run on ctrs, whatever docker context is in use; the images are in ctrs, not {o}. `ctrs build-with docker` switches back"),
        (Some("ctrs"), None) => println!("docker build and docker compose build run on ctrs (builder `{builder}`)"),
        (_, o) => println!(
            "docker build follows docker's context{}: on ctrs when docker uses ctrs. `ctrs build` always builds on ctrs; `ctrs build-with ctrs` sends every build to ctrs",
            o.map(|o| format!(" ({o}'s builds stay {o}'s)")).unwrap_or_default()
        ),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn places(dir: &Path) -> Places {
        let docker = dir.join(".docker");
        Places { buildx: docker.join("buildx"), docker, state: dir.join(".ctrs/build.json"), builder: "ctrs-build".into(), context: "ctrs".into() }
    }

    fn scratch(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ctrs-buildwith-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn builder(p: &Places) {
        let i = json!({"Name": "ctrs-build", "Driver": "docker-container", "Nodes": [{"Name": "ctrs-build0", "Endpoint": "ctrs", "DriverOpts": {"default-load": "true"}}], "Dynamic": false});
        write_bytes(&p.instance("ctrs-build"), i.to_string().as_bytes()).unwrap();
    }

    fn read(path: &Path) -> Option<String> {
        std::fs::read_to_string(path).ok()
    }

    #[test]
    fn a_fresh_machine_builds_with_ctrs_and_back_leaves_nothing() {
        let d = scratch("fresh");
        let p = places(&d);
        // Before the builder exists: chosen, taken later.
        p.apply(None).unwrap();
        assert_eq!(p.saved(), Some(With::Ctrs));
        assert!(!p.taken());
        builder(&p);
        p.apply(None).unwrap();
        assert!(p.taken());
        let copy = read_json(&p.instance("ctrs")).unwrap();
        assert_eq!((copy["Name"].as_str(), copy["Nodes"][0]["Name"].as_str()), (Some("ctrs"), Some("ctrs-build0")));
        assert_eq!(read_json(&p.current()).unwrap(), json!({"Key": "ctrs", "Name": "ctrs-build", "Global": true}));
        assert!(!p.ask(None));
        // Docker Desktop installed afterwards: asked once.
        assert!(p.ask(Some("Docker Desktop")));
        p.choose(With::Docker).unwrap();
        assert!(!p.ask(Some("Docker Desktop")));
        assert!(!p.taken());
        assert_eq!(read_json(&p.config()).unwrap(), json!({}));
        assert!(!p.current().exists());
        // The context's builder stays: it serves `docker --context ctrs build`.
        assert!(p.instance("ctrs").is_file());
    }

    #[test]
    fn a_second_ctrs_whose_app_is_gone_hands_builds_back_to_the_first() {
        let d = scratch("second");
        let main = places(&d);
        builder(&main);
        main.choose(With::Ctrs).unwrap();
        // A development build of ctrs, its own state and builder, takes them.
        let dev = Places { state: d.join(".ctrs-layers/build.json"), builder: "ctrs-layers-build".into(), context: "ctrs-layers".into(), ..places(&d) };
        let i = json!({"Name": "ctrs-layers-build", "Driver": "docker-container", "Nodes": [{"Name": "ctrs-layers-build0", "Endpoint": "ctrs-layers"}], "Dynamic": false});
        write_bytes(&dev.instance("ctrs-layers-build"), i.to_string().as_bytes()).unwrap();
        dev.choose(With::Ctrs).unwrap();
        assert!(dev.taken() && !main.taken());
        // Its app deleted: the daemon hands back (daemon/mod.rs).
        dev.give_back().unwrap();
        assert!(main.taken(), "builds go to the first ctrs again");
        assert_eq!(dev.saved(), Some(With::Ctrs), "the choice stays");
        // Taken up again, it takes them again.
        dev.apply(None).unwrap();
        assert!(dev.taken());
    }

    #[test]
    fn switching_back_restores_exactly() {
        let d = scratch("restore");
        let p = places(&d);
        builder(&p);
        let cfg = json!({"auths": {"ghcr.io": {}}, "currentContext": "orbstack", "aliases": {"foo": "bar"}});
        write_json(&p.config(), &cfg).unwrap();
        let current = r#"{"Key":"orbstack","Name":"mine","Global":false}"#;
        write_bytes(&p.current(), current.as_bytes()).unwrap();
        // Another engine: nothing happens until asked.
        p.apply(Some("OrbStack")).unwrap();
        assert!(p.ask(Some("OrbStack")));
        assert_eq!(read(&p.current()).as_deref(), Some(current));
        assert_eq!(read_json(&p.config()).unwrap(), cfg);
        p.choose(With::Ctrs).unwrap();
        assert!(p.taken());
        assert_eq!(read_json(&p.config()).unwrap()["aliases"], json!({"foo": "bar", "builder": "buildx"}));
        // Choosing again keeps the first snapshot.
        p.choose(With::Ctrs).unwrap();
        p.choose(With::Docker).unwrap();
        assert_eq!(read_json(&p.config()).unwrap(), cfg);
        assert_eq!(read(&p.current()).as_deref(), Some(current));
        assert_eq!(p.status(Some("OrbStack"))["with"], "docker");
    }

    #[test]
    fn an_alias_of_the_users_own_comes_back() {
        let d = scratch("alias");
        let p = places(&d);
        builder(&p);
        write_json(&p.config(), &json!({"aliases": {"builder": "mybuilder"}})).unwrap();
        p.choose(With::Ctrs).unwrap();
        assert_eq!(read_json(&p.config()).unwrap()["aliases"]["builder"], "buildx");
        p.choose(With::Docker).unwrap();
        assert_eq!(read_json(&p.config()).unwrap(), json!({"aliases": {"builder": "mybuilder"}}));
        // An empty `aliases` that was there stays.
        write_json(&p.config(), &json!({"aliases": {}})).unwrap();
        p.choose(With::Ctrs).unwrap();
        p.choose(With::Docker).unwrap();
        assert_eq!(read_json(&p.config()).unwrap(), json!({"aliases": {}}));
    }

    #[test]
    fn a_change_made_since_is_left_alone() {
        let d = scratch("since");
        let p = places(&d);
        builder(&p);
        p.choose(With::Ctrs).unwrap();
        // `docker buildx use other` afterwards: apply doesn't take it back.
        let theirs = r#"{"Key":"ctrs","Name":"other","Global":false}"#;
        write_bytes(&p.current(), theirs.as_bytes()).unwrap();
        p.apply(None).unwrap();
        assert_eq!(read(&p.current()).as_deref(), Some(theirs));
        // Back to Docker: their builder stays, the alias goes.
        p.choose(With::Docker).unwrap();
        assert_eq!(read(&p.current()).as_deref(), Some(theirs));
        assert_eq!(read_json(&p.config()).unwrap(), json!({}));
    }

    #[test]
    fn a_builder_of_another_name_ctrs_is_not_replaced() {
        let d = scratch("foreign");
        let p = places(&d);
        builder(&p);
        let foreign = json!({"Name": "ctrs", "Driver": "remote", "Nodes": [{"Name": "ctrs0", "Endpoint": "tcp://x:1234"}]});
        write_json(&p.instance("ctrs"), &foreign).unwrap();
        p.choose(With::Docker).unwrap();
        assert_eq!(read_json(&p.instance("ctrs")).unwrap(), foreign);
        p.give_back().unwrap();
        assert!(p.instance("ctrs").is_file());
    }

}
