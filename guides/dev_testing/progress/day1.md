https://developers.google.com/health/get-started

Access to the Google Health API is provided through Google Cloud. To enable the API and authorize a Google Account, you'll need a Google Cloud project.

Whether you are an existing Fitbit API developer, or new to the Google Health API, you'll need to complete this step in order to make calls to the API.

So the way to connect to Google Fitbit API is going to be with Auth
Google Cloud -> Google Health -> Google Fitbit API -> OAuth 2.0 Client ID (Grants Permission, Send Client ID + Secret to the server (passkey) to a Authorization Server)

OAuth 2.0 Client ID -> a way of vertification to allow your app to log into the server 
Right now I'm limited to a 100 users for training and production, have to add them to an email list

What scopes will the app use? 
https://github.com/googleapis/google-api-python-client


URI Link -> is a just a link that redirects users back to a home page , send users back to an application after loging in

This is my URI link: https://www.google.com/?code=4/0Ab32j93oyGWqaXE112sP1IKmh3kV1fE4tcHIMXYJQYWgNEtAa_0-YsfkS9Ekj3Be89u3fw&scope=https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly, I got this after Sucessful Auth

In production it should parse between code & scope in the URI! 

https://www.google.com/?code=4/0Ab32j93oyGWqaXE112sP1IKmh3kV1fE4tcHIMXYJQYWgNEtAa_0-YsfkS9Ekj3Be89u3fw&scope=https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly

this is my authorization code; 4/0Ab32j93oyGWqaXE112sP1IKmh3kV1fE4tcHIMXYJQYWgNEtAa_0-YsfkS9Ekj3Be89u3fw



I got AUTH Working! Noice!!!
https://developers.google.com/health/codelabs/make-your-first-api-call#3

 "exercise": {
        "interval": {
          "startTime": "2026-08-11T20:40:32Z",
          "startUtcOffset": "-18000s",
          "endTime": "2026-08-11T21:41:05.600Z",
          "endUtcOffset": "-18000s"
        },
        "exerciseType": "WALKING",
        "metricsSummary": {
          "caloriesKcal": 542,
          "distanceMillimeters": 3248500,
          "steps": "4699",
          "averagePaceSecondsPerMeter": 1.1183623210712637,
          "averageHeartRateBeatsPerMinute": "126",
          "activeZoneMinutes": "56",
          "heartRateZoneDurations": {
            "lightTime": "720s",
            "moderateTime": "2460s",
            "vigorousTime": "480s",
            "peakTime": "0s"
          }
        },
        "exerciseMetadata": {},
        "displayName": "Walk",
        "activeDuration": "3633.600s",
        "updateTime": "2026-08-11T22:08:30.596144Z",
        "createTime": "2026-08-11T22:08:30.596144Z"
      }
    },

things to think about 
-> Calling this on a scheduler + token access ...? Getting all activites (future use)
for now let's focus on running + walking for steps :)

