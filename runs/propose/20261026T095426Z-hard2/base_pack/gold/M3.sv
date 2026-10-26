// Gold testbench for M3 (R7 + T2 in one run).
// Both modules at prescale 16'hFFFF in one testbench: the receiver takes A5
// while the transmitter sends 5A, in parallel so the run stays within one
// frame time (~5.2M clocks). Self-checking: the received word and every
// transmitted bit.
`timescale 1ns / 1ps

module tb;

  localparam logic [15:0] PRESCALE = 16'hFFFF;
  localparam int BIT = 65535 * 8;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, rx_busy, overrun_error, frame_error;
  wire         s_axis_tready, txd, tx_busy;

  always #4 clk = ~clk;

  uart_rx rx (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .rxd(rxd), .busy(rx_busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(PRESCALE)
  );

  uart_tx tx (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(tx_busy),
    .prescale(PRESCALE)
  );

  // Drive on the falling edge so inputs are stable at every rising edge.
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic receive_a5();
    logic [7:0] d = 8'hA5;
    rxd = 1'b0; repeat (BIT) @(negedge clk);
    for (int i = 0; i < 8; i++) begin rxd = d[i]; repeat (BIT) @(negedge clk); end
    rxd = 1'b1; repeat (BIT) @(negedge clk);
    repeat (10) @(negedge clk);
    if (!(m_axis_tvalid && m_axis_tdata == 8'hA5)) $fatal(1, "rx: A5 not received");
    if (frame_error || overrun_error) $fatal(1, "rx: unexpected error");
  endtask

  task automatic send_5a();
    logic [7:0] d = 8'h5A;
    int n = 0;
    while (s_axis_tready !== 1'b1) begin
      @(negedge clk);
      n++;  // not ++n inside the condition: Verilator 5.020 internal error
      if (n > 20) $fatal(1, "tx: no tready");
    end
    s_axis_tdata = d; s_axis_tvalid = 1'b1;
    @(negedge clk);
    s_axis_tvalid = 1'b0;
    repeat (BIT / 2) @(negedge clk);  // middle of each bit from here on
    if (txd !== 1'b0) $fatal(1, "tx: no start bit");
    for (int i = 0; i < 8; i++) begin
      repeat (BIT) @(negedge clk);
      if (txd !== d[i]) $fatal(1, "tx: data bit %0d is %b", i, txd);
    end
    repeat (BIT) @(negedge clk);
    if (txd !== 1'b1) $fatal(1, "tx: no stop bit");
    repeat (BIT) @(negedge clk);
    if (tx_busy) $fatal(1, "tx: still busy after the frame");
  endtask

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(3);
    fork
      receive_a5();
      send_5a();
    join
    $display("PASS gold M3");
    $finish;
  end

  initial begin
    #100ms;
    $fatal(1, "timeout");
  end

endmodule
