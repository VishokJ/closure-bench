`timescale 1ns / 1ps

module tb;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = 16'd1;   // 8 clocks per bit
  wire         s_axis_tready;
  wire         txd;
  wire         busy;

  always #4 clk = ~clk;

  uart_tx dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  // Handshake: returns on the falling edge right after the accepting rising edge.
  task automatic axis_send(input logic [7:0] b);
    bit ready;
    int guard;
    guard = 0;
    s_axis_tdata  = b;
    s_axis_tvalid = 1'b1;
    do begin
      ready = s_axis_tready;
      @(negedge clk);
      guard++;
      if (guard > 1000) $fatal(1, "tready never asserted");
    end while (!ready);
    s_axis_tvalid = 1'b0;
  endtask

  // Called on the falling edge right after the handshake (start bit begins).
  task automatic recv_check(input logic [7:0] exp_b);
    logic [7:0] b;
    if (txd !== 1'b0) $fatal(1, "start bit not driven after handshake");
    wait_clks(4);
    if (txd !== 1'b0) $fatal(1, "start bit not low at mid-bit");
    for (int i = 0; i < 8; i++) begin
      wait_clks(8);
      b[i] = txd;
    end
    wait_clks(8);
    if (txd !== 1'b1) $fatal(1, "missing stop bit");
    if (b !== exp_b) $fatal(1, "got 0x%02h, expected 0x%02h", b, exp_b);
  endtask

  initial begin
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(4);
    if (txd !== 1'b1 || busy !== 1'b0) $fatal(1, "not idle after reset");

    // Start a frame, then reset during the start bit.
    axis_send(8'h3C);
    if (txd !== 1'b0 || busy !== 1'b1) $fatal(1, "frame did not start");
    wait_clks(2);
    if (txd !== 1'b0 || busy !== 1'b1) $fatal(1, "not mid start bit before reset");
    rst = 1'b1;
    wait_clks(1);
    if (txd !== 1'b1) $fatal(1, "txd not at mark after reset");
    if (busy !== 1'b0) $fatal(1, "busy not cleared by reset");
    if (s_axis_tready !== 1'b0) $fatal(1, "tready not cleared by reset");
    rst = 1'b0;

    // Line must stay at mark: aborted frame must not resume.
    for (int i = 0; i < 100; i++) begin
      @(negedge clk);
      if (txd !== 1'b1 || busy !== 1'b0) $fatal(1, "aborted frame resumed after reset");
    end

    // A later byte is transmitted correctly.
    axis_send(8'hA5);
    recv_check(8'hA5);
    wait_clks(20);
    if (txd !== 1'b1 || busy !== 1'b0) $fatal(1, "not idle after final frame");

    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end

endmodule
