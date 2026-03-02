Phisical Label Raspberry	Host Name	User Name	User Password	Given SSID	SSID Password	IP_Adress
1	grid1	grid1	12345678	irfanPhone	12345678	192.168.137.9
2	grid2	grid2	12345678	irfanPhone	12345678	192.168.137.86
3	grid3	grid3	12345678	irfanPhone	12345678	192.168.137.113
4	grid4	grid4	12345678	irfanPhone	12345678	192.168.137.68
5	grid5	grid5	12345678	irfanPhone	12345678	192.168.137.65
6	grid6	grid6	12345678	irfanPhone	12345678	192.168.137.98



Apps						
Phisical Label Raspberry	App Name	Port	User Name	Password	Docker Network	Container Name
1	Graphana	3000	admin	admin	influxdb	scada_dashboard
1	Node-Red	1880	-	-	influxdb	scada_logic
1	Influx_DB	8086	-	-	influxdb	scada_historian