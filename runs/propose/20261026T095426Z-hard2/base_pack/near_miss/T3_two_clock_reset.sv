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
    wait_clks(1);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(3);
    if (s_axis_tready !== 1'b1) $fatal(1, "idle transmitter should have tready high");

    // Reset held for only two rising edges: one clock short of the cover.
    rst = 1'b1;
    wait_clks(1);
    if (s_axis_tready !== 1'b0) $fatal(1, "tready high after first reset clock");
    wait_clks(1);
    if (s_axis_tready !== 1'b0) $fatal(1, "tready high after second reset clock");
    rst = 1'b0;
    wait_clks(1);
    if (s_axis_tready !== 1'b1) $fatal(1, "tready did not return after reset");

    $display("near miss done");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
