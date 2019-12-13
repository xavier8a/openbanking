# Getting Started with Core Banking API v1.0.0

Welcome to Mock API for banking services.

The following instructions are for deploying the application as a Cloud Foundry application. To deploy as a container to **IBM Cloud Kubernetes Service** instead, [see README-kubernetes.md](README-kubernetes.md)

## Prerequisites

You'll need the following:
* [IBM Cloud account](https://console.ng.bluemix.net/registration/)
* [Cloud Foundry CLI](https://github.com/cloudfoundry/cli#downloads)
* [Git](https://git-scm.com/downloads)
* [Python](https://www.python.org/downloads/)

## 1. Clone the sample app

Now you're ready to start working with the app. Clone the repo and change to the directory where the sample app is located.
  ```
git clone https://github.com/xavier8a/openbanking.git
cd openbanking
  ```

  Peruse the files in the *get-started-python* directory to familiarize yourself with the contents.

## 2. Run the app locally

Install the dependencies listed in the [requirements.txt](https://pip.readthedocs.io/en/stable/user_guide/#requirements-files) file to be able to run the app locally.

You can optionally use a [virtual environment](https://packaging.python.org/installing/#creating-and-using-virtual-environments) to avoid having these dependencies clash with those of other Python projects or your operating system.
  ```
pip install -r requirements.txt
  ```

Run the app.
  ```
python3 server_japronto.py
  ```

 View your app at: http://localhost:8080

## 4. Create environment variables

To execute openbanking, you need to create environment variables first.

  ```

export REDIS_SERVER=127.0.0.1
export REDIS_PORT=6379
export REDIS_PASSWORD=
export REDIS_POOL=7
export PORT=8080

  ```

## 5. Prepare the app for deployment

To deploy to IBM Cloud, it can be helpful to set up a manifest.yml file. One is provided for you with the sample. Take a moment to look at it.

The manifest.yml includes basic information about your app, such as the name, how much memory to allocate for each instance and the route. In this manifest.yml **random-route: true** generates a random route for your app to prevent your route from colliding with others.  You can replace **random-route: true** with **host: myChosenHostName**, supplying a host name of your choice. [Learn more...](https://console.bluemix.net/docs/manageapps/depapps.html#appmanifest)
 ```
 applications:
 - name: openbanking
   random-route: true
   memory: 128M
 ```

## 6. Deploy the app

You can use the Cloud Foundry CLI to deploy apps.

Choose your API endpoint
   ```
cf api <API-endpoint>
   ```

Replace the *API-endpoint* in the command with an API endpoint from the following list.

|URL                             |Region          |
|:-------------------------------|:---------------|
| https://api.ng.bluemix.net     | US South       |
| https://api.eu-de.bluemix.net  | Germany        |
| https://api.eu-gb.bluemix.net  | United Kingdom |
| https://api.au-syd.bluemix.net | Sydney         |

Login to your IBM Cloud account

  ```
cf login
  ```

From within the *openbanking* directory push your app to IBM Cloud
  ```
cf push 
  ```

This can take a minute. If there is an error in the deployment process you can use the command `cf logs <Your-App-Name> --recent` to troubleshoot.

When deployment completes you should see a message indicating that your app is running.  View your app at the URL listed in the output of the push command.  You can also issue the
  ```
cf apps
  ```
  command to view your apps status and see the URL.

## 5. Create your environment variables

Next, we'll add a NoSQL database to this application and set up the application so that it can run locally and on IBM Cloud.

1. Log in to IBM Cloud in your Browser. Browse to the `Dashboard`. Select your application by clicking on its name in the `Name` column.
2. Click on `Connections` then `Connect new`.
2. In the `Data & Analytics` section, select `Cloudant NoSQL DB` and `Create` the service.
3. Select `Restage` when prompted. IBM Cloud will restart your application and provide the database credentials to your application using the `VCAP_SERVICES` environment variable. This environment variable is only available to the application when it is running on IBM Cloud.

Environment variables enable you to separate deployment settings from your source code. For example, instead of hardcoding a database password, you can store this in an environment variable which you reference in your source code. [Learn more...](/docs/manageapps/depapps.html#app_env)

1. Run your application locally.
  ```
python3 server_japronto.py
  ```

  View your app at: http://localhost:8080. Any names you enter into the app will now get added to the database.

2. Make any changes you want and re-deploy to IBM Cloud!
  ```
cf push -t 180
  ```

  View your app at the URL listed in the output of the push command, for example, *myUrl.mybluemix.net*.
