This project is a test bed for FLSA (Federated Learning Simulation and Analysis) project.
In this Project 6 Raspberry Pi 5 used. 3 of the raspbery pi has 2 arduino unos s3 clone each. 
Our purpose in this project is RPİ-1 will be the scada monitor like in the factory.RPİ-3,RPİ-4,RPİ-5 will be the devices that manages the arduinos, they will get the data from the arduinos and send it to the scada directly. 
RPİ-2 will be the agregator serverr. ın the RPİ-3,RPİ-4,RPİ-5 there will be Fedareted Learning Client work. Theese models will send their weights to the agregator serverr which is RPİ-2.RPİ-2 will aggregate the weights and send them back to the clients.
RPİ-6 will be the act as a network monitor and use suricata to monitor the network traffic.  