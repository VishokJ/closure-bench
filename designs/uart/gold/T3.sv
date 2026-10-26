`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = 16'd2;
  wire         s_axis_tready;
  wire         txd;
  wire         busy;

  always #4 clk = ~clk;

  uart_tx dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy), .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  initial begin
    logic [7:0] b;
    wait_clks(1);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(3);
    if (s_axis_tready !== 1'b1) $fatal(1, "idle transmitter should have tready high");
    if (txd !== 1'b1) $fatal(1, "txd should idle high");
    if (busy !== 1'b0) $fatal(1, "busy should be low when idle");

    // Hold reset for four rising edges; tready must stay low throughout.
    rst = 1'b1;
    for (int i = 0; i < 4; i++) begin
      wait_clks(1);
      if (s_axis_tready !== 1'b0) $fatal(1, "tready high during reset (clock %0d)", i);
      if (txd !== 1'b1) $fatal(1, "txd not high during reset");
      if (busy !== 1'b0) $fatal(1, "busy high during reset");
    end
    rst = 1'b0;
    wait_clks(1);
    if (s_axis_tready !== 1'b1) $fatal(1, "tready did not return after reset");

    // Transmitter still works after the reset.
    s_axis_tdata  = 8'hA5;
    s_axis_tvalid = 1'b1;
    wait_clks(1);
    s_axis_tvalid = 1'b0;
    if (txd !== 1'b0) $fatal(1, "start bit not driven");
    wait_clks(7);
    if (txd !== 1'b0) $fatal(1, "start bit not low at mid-bit");
    for (int i = 0; i < 8; i++) begin
      wait_clks(16);
      b[i] = txd;
    end
    wait_clks(16);
    if (txd !== 1'b1) $fatal(1, "missing stop bit");
    if (b !== 8'hA5) $fatal(1, "got 0x%02h, expected 0xA5", b);

    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
